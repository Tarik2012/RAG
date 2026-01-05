from documents.services.text_extractor import extract_text_from_document
from documents.services.chunker import chunk_text
from documents.services.chunk_persister import persist_chunks


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

        # Estado: processed
        document.status = "processed"
        document.save(update_fields=["status"])

        return len(chunks)

    except Exception:
        # Estado: failed
        document.status = "failed"
        document.save(update_fields=["status"])
        raise
