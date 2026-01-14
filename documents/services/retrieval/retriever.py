import math
from typing import List, Tuple

from documents.models import DocumentChunk
from documents.services.embeddings.embedding_provider import EmbeddingProvider


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


class Retriever:
    def __init__(self, embedding_provider: EmbeddingProvider):
        self.embedding_provider = embedding_provider

    def retrieve(
        self,
        *,
        query: str,
        top_k: int = 5,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Devuelve los top_k chunks más similares a la query,
        junto con su score de similitud.
        """

        # 1. Embedding de la query
        query_embedding = self.embedding_provider.embed_texts([query])[0]

        # 2. Cargar chunks embebidos
        chunks = DocumentChunk.objects.filter(
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
