import logging
from typing import List, Optional, Tuple

from pgvector.django import CosineDistance

from documents.models import Document, DocumentChunk
from documents.services.embeddings.embedding_provider import EmbeddingProvider
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)


def _expand_or_fallback(query_rewriter, query):
    if not query_rewriter:
        return [query]
    try:
        return query_rewriter.expand(query)
    except Exception as exc:
        logger.warning("Query expansion falló, usando query original: %s", exc)
        return [query]


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
        document_ids: Optional[List[int]] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Devuelve los top_k chunks más similares de los documentos del usuario.
        Por defecto busca en TODOS los documentos procesados del usuario (el "proyecto").
        Si se pasa document_ids, acota la búsqueda a esos documentos.
        """
        base_chunks = DocumentChunk.objects.filter(
            document__owner=user,
            document__status="processed",
            embedding_status="embedded",
            embedding_vector__isnull=False,
        )
        if document_ids:
            base_chunks = base_chunks.filter(document_id__in=document_ids)

        if not base_chunks.exists():
            return []

        queries = _expand_or_fallback(self.query_rewriter, query)
        query_embeddings = self.embedding_provider.embed_texts(queries)

        best_by_chunk: dict[int, Tuple[DocumentChunk, float]] = {}
        for q_emb in query_embeddings:
            candidates = (
                base_chunks
                .annotate(distance=CosineDistance("embedding_vector", q_emb))
                .order_by("distance")[:20]
            )
            for chunk in candidates:
                dist = float(chunk.distance)
                current = best_by_chunk.get(chunk.id)
                if current is None or dist < current[1]:
                    best_by_chunk[chunk.id] = (chunk, dist)

        merged = sorted(best_by_chunk.values(), key=lambda item: item[1])
        scored_chunks: List[Tuple[DocumentChunk, float]] = [
            (chunk, 1.0 - dist)
            for chunk, dist in merged
            if (1.0 - dist) >= 0.10
        ][:20]
        if not scored_chunks:
            return []

        if self.reranker is not None:
            texts = [chunk.text for chunk, _ in scored_chunks]
            reranked_texts = self.reranker.rerank(query, texts)
            remaining_by_text: dict[str, List[Tuple[DocumentChunk, float]]] = {}
            for chunk, score in scored_chunks:
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
