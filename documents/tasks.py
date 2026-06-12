from celery import shared_task
from django.db import transaction

from documents.models import Document
from documents.services.document_processor import process_document
from documents.services.documentation.documentation_service import DocumentationService
from documents.services.llm.openai_llm_provider import OpenAILLMProvider


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


@shared_task(bind=True)
def generate_documentation_task(self, document_id: int):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return

    document.documentation_status = "processing"
    document.save(update_fields=["documentation_status"])

    try:
        llm_provider = OpenAILLMProvider()
        service = DocumentationService(llm_provider=llm_provider)
        result = service.generate(document_id=document.id, user=document.owner)

        if "error" in result:
            document.documentation_status = "failed"
            document.save(update_fields=["documentation_status"])
            return

        document.documentation = result["documentation"]
        document.documentation_status = "ready"
        document.save(update_fields=["documentation", "documentation_status"])
    except Exception:
        document.documentation_status = "failed"
        document.save(update_fields=["documentation_status"])
        raise
