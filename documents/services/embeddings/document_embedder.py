from documents.models import Document, DocumentChunk
from documents.services.embeddings.chunk_embedder import ChunkEmbedder


class DocumentEmbedder:
    def __init__(self, chunk_embedder: ChunkEmbedder):
        self.chunk_embedder = chunk_embedder

    def embed_document(self, document: Document) -> int:
        """
        Embebe todos los chunks pendientes de un documento.
        Devuelve el número de chunks procesados.
        """

        pending_chunks = (
            DocumentChunk.objects
            .filter(
                document=document,
                embedding_status="pending",
            )
            .order_by("order")
        )

        chunks = list(pending_chunks)
        if not chunks:
            return 0

        self.chunk_embedder.embed_chunks(chunks)
        return len(chunks)
