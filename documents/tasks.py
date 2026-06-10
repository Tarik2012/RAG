from celery import shared_task
from django.db import transaction

from documents.models import Document
from documents.services.document_processor import process_document


@shared_task(bind=True)
def process_document_task(self, document_id: int):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return

    try:
        with transaction.atomic():
            process_document(document)
    except Exception:
        document.status = "failed"
        document.save(update_fields=["status"])
        raise
