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
        Document.set_active_for_user(document=document)

    except Exception:
        # process_document ya marca el documento como "failed"
        raise
