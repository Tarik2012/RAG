import math
from typing import List, Optional, Tuple

from documents.models import Document, DocumentChunk
from documents.services.embeddings.embedding_provider import EmbeddingProvider
from documents.services.retrieval.query_rewriter import QueryRewriter


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


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
    ):
        self.embedding_provider = embedding_provider
        self.query_rewriter = query_rewriter

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
        """

        # 0. Documento activo del usuario
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

        # 1. Embedding de la query
        query_embedding = self.embedding_provider.embed_texts(
            [rewritten_query]
        )[0]

        # 2. Cargar SOLO chunks del documento activo
        chunks = DocumentChunk.objects.filter(
            document=active_document,
            embedding_status="embedded",
            embedding__isnull=False,
        )

        # 3. Calcular similitud
        scored_chunks: List[Tuple[DocumentChunk, float]] = []
        for chunk in chunks:
            score = cosine_similarity(query_embedding, chunk.embedding)
            scored_chunks.append((chunk, score))

        # 4. Ordenar por score descendente
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        return scored_chunks[:top_k]
