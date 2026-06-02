from typing import List, Optional, Tuple

from pgvector.django import CosineDistance

from documents.models import Document, DocumentChunk
from documents.services.embeddings.embedding_provider import EmbeddingProvider
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker


class Retriever:
    """
    Retriever profesional y seguro:
    - Document-scoped
    - Sin mezcla de fuentes
    - Determinista
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        query_rewriter: Optional[QueryRewriter] = None,
        reranker: Optional[CrossEncoderReranker] = None,
    ):
        self.embedding_provider = embedding_provider
        self.query_rewriter = query_rewriter
        self.reranker = reranker

    def retrieve(
        self,
        *,
        query: str,
        user,
        top_k: int = 6,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Devuelve los top_k chunks MÁS similares
        SOLO del documento activo del usuario.
        La búsqueda por similitud la hace Postgres con pgvector.
        """

        active_document = Document.objects.filter(
            owner=user,
            is_active=True,
            status="processed",
        ).first()

        if active_document is None:
            return []

        rewritten_query = query
        if self.query_rewriter is not None:
            rewritten_query = self.query_rewriter.rewrite(query)

        query_embedding = self.embedding_provider.embed_texts(
            [rewritten_query]
        )[0]

        # Búsqueda vectorial en Postgres: orden por distancia coseno ascendente
        candidates = (
            DocumentChunk.objects
            .filter(
                document=active_document,
                embedding_status="embedded",
                embedding_vector__isnull=False,
            )
            .annotate(distance=CosineDistance("embedding_vector", query_embedding))
            .order_by("distance")[:20]
        )

        # distancia coseno = 1 - similitud coseno
        scored_chunks: List[Tuple[DocumentChunk, float]] = [
            (chunk, 1.0 - float(chunk.distance))
            for chunk in candidates
            if (1.0 - float(chunk.distance)) >= 0.10
        ]

        if not scored_chunks:
            return []

        if self.reranker is not None:
            candidate_chunks = scored_chunks[:20]
            texts = [chunk.text for chunk, _ in candidate_chunks]
            reranked_texts = self.reranker.rerank(rewritten_query, texts)

            remaining_by_text: dict[str, List[Tuple[DocumentChunk, float]]] = {}
            for chunk, score in candidate_chunks:
                remaining_by_text.setdefault(chunk.text, []).append((chunk, score))

            reranked_chunks: List[Tuple[DocumentChunk, float]] = []
            for text in reranked_texts:
                matches = remaining_by_text.get(text)
                if not matches:
                    continue
                chunk, _ = matches.pop(0)
                reranked_chunks.append((chunk, 1.0))

            return reranked_chunks[:top_k]

        return scored_chunks[:top_k]
