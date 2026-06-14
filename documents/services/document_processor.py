from django.db import transaction

from documents.services.text_extractor import extract_text_from_document
from documents.services.chunker import chunk_text
from documents.services.chunk_persister import persist_chunks
from documents.services.embeddings.document_embedder import DocumentEmbedder
from documents.services.embeddings.chunk_embedder import ChunkEmbedder
from documents.services.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider


def process_document(document) -> int:
    """
    Procesa un documento completo: extrae texto, divide en chunks,
    persiste y genera embeddings.

    Las actualizaciones de estado quedan FUERA de la transaccion para que
    'processing' sea visible de inmediato a otros procesos. Solo persist_chunks
    + embeddings van dentro de atomic() (deben ser todo-o-nada juntos).
    """
    try:
        document.status = "processing"
        document.save(update_fields=["status"])

        text = extract_text_from_document(document)
        if not text.strip():
            raise ValueError("Empty extracted text")

        chunks = chunk_text(text)

        with transaction.atomic():
            persist_chunks(document, chunks)
            embedding_provider = OpenAIEmbeddingProvider()
            chunk_embedder = ChunkEmbedder(
                embedding_provider,
                model_name=embedding_provider.model_name,
            )
            document_embedder = DocumentEmbedder(chunk_embedder)
            document_embedder.embed_document(document)

        document.status = "processed"
        document.save(update_fields=["status"])

        return len(chunks)

    except Exception:
        document.status = "failed"
        document.save(update_fields=["status"])
        raise
