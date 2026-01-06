from typing import Iterable, List

from django.db import transaction
from django.utils import timezone

from documents.models import DocumentChunk
from documents.services.embeddings.embedding_provider import EmbeddingProvider


class ChunkEmbedder:
    def __init__(self, provider: EmbeddingProvider, *, model_name: str):
        self.provider = provider
        self.model_name = model_name

    def embed_chunks(self, chunks: Iterable[DocumentChunk]) -> None:
        """
        Genera embeddings para los chunks proporcionados.
        Solo se debe llamar con chunks pendientes o reprocesables.
        """

        chunks = list(chunks)
        if not chunks:
            return

        texts: List[str] = [chunk.text for chunk in chunks]

        embeddings = self.provider.embed_texts(texts)

        if len(embeddings) != len(chunks):
            raise ValueError("EmbeddingProvider returned invalid number of embeddings")

        now = timezone.now()

        with transaction.atomic():
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding
                chunk.embedding_status = "embedded"
                chunk.embedding_model = self.model_name
                chunk.embedded_at = now
                chunk.save(
                    update_fields=[
                        "embedding",
                        "embedding_status",
                        "embedding_model",
                        "embedded_at",
                    ]
                )
