import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from documents.models import Document
from documents.services.document_processor import process_document
from documents.services.github.repo_ingestor import ingest_repo_file
from documents.services.github.repo_reader import list_repo_code_files
from documents.services.documentation.documentation_service import DocumentationService
from documents.services.llm.openai_llm_provider import OpenAILLMProvider

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_document_task(self, document_id: int):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return

    if document.status == "processed":
        return

    process_document(document)


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


@shared_task(bind=True)
def ingest_repo_task(self, owner: str, repo: str, user_id: int) -> int:
    user = get_user_model().objects.get(id=user_id)
    paths = list_repo_code_files(owner, repo)
    created = 0
    for path in paths:
        try:
            ingest_repo_file(owner=owner, repo=repo, path=path, user=user)
            created += 1
        except Exception:
            logger.exception("Fallo al ingerir %s de %s/%s", path, owner, repo)
            continue
    return created
