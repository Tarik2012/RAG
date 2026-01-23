from documents.services.text_extractor import extract_text_from_document
from documents.services.chunker import chunk_text
from documents.services.chunk_persister import persist_chunks
from documents.services.embeddings.document_embedder import DocumentEmbedder
from documents.services.embeddings.chunk_embedder import ChunkEmbedder
from documents.services.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider


def process_document(document) -> int:
    """
    Procesa un documento completo:
    1. Extrae texto
    2. Divide en chunks
    3. Guarda chunks en BD

    Controla estados y errores.
    """

    try:
        # Estado: processing
        document.status = "processing"
        document.save(update_fields=["status"])

        # 1. Extraer texto
        text = extract_text_from_document(document)

        if not text.strip():
            raise ValueError("Empty extracted text")

        # 2. Chunking
        chunks = chunk_text(text)

        # 3. Persistir (idempotente)
        persist_chunks(document, chunks)

        # 4. Embeddings
        embedding_provider = OpenAIEmbeddingProvider()
        chunk_embedder = ChunkEmbedder(
            embedding_provider,
            model_name=embedding_provider.model_name,
        )
        document_embedder = DocumentEmbedder(chunk_embedder)
        document_embedder.embed_document(document)

        # Estado: processed
        document.status = "processed"
        document.save(update_fields=["status"])

        return len(chunks)

    except Exception:
        # Estado: failed
        document.status = "failed"
        document.save(update_fields=["status"])
        raise
