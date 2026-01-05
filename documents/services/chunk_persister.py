from django.db import transaction
from documents.models import Document, DocumentChunk


def persist_chunks(document: Document, chunks: list[str]) -> None:
    """
    Guarda los chunks de un documento en la base de datos.
    Si ya existen chunks previos, los elimina.
    """

    with transaction.atomic():
        # Eliminar chunks anteriores (reprocesado seguro)
        document.chunks.all().delete()

        objects = [
            DocumentChunk(
                document=document,
                order=index,
                text=chunk,
            )
            for index, chunk in enumerate(chunks)
        ]

        DocumentChunk.objects.bulk_create(objects)
