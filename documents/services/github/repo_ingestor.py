from django.core.files.base import ContentFile

from documents.models import Document
from documents.services.github.repo_reader import fetch_file_content


def ingest_repo_file(*, owner: str, repo: str, path: str, user, branch: str | None = None) -> Document:
    """Crea un Document a partir de un archivo del repo y lanza su ingesta."""
    from documents.tasks import process_document_task

    content = fetch_file_content(owner, repo, path, branch)
    document = Document(
        owner=user,
        original_name=f"{repo}/{path}",
        source=f"github:{owner}/{repo}",
        content_type="text/plain",
        size=len(content.encode("utf-8")),
        status="uploaded",
    )
    safe_name = path.replace("/", "_")
    document.file.save(safe_name, ContentFile(content.encode("utf-8")), save=False)
    document.save()
    process_document_task.delay(document.id)
    return document
