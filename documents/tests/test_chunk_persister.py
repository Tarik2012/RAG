import pytest

from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
from documents.services.chunk_persister import persist_chunks


pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="tester",
        password="pass1234",
    )


@pytest.fixture
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def document_factory(user, media_root):
    def _create_document():
        uploaded = SimpleUploadedFile(
            "test.pdf",
            b"%PDF-1.4\n%EOF",
            content_type="application/pdf",
        )
        return Document.objects.create(
            owner=user,
            original_name="test.pdf",
            file=uploaded,
            content_type="application/pdf",
            size=uploaded.size,
            status="uploaded",
        )

    return _create_document


def test_persist_chunks_replaces_previous_chunks(document_factory):
    document = document_factory()

    DocumentChunk.objects.bulk_create(
        [
            DocumentChunk(document=document, order=0, text="old-1"),
            DocumentChunk(document=document, order=1, text="old-2"),
        ]
    )

    persist_chunks(document, ["new-1", "new-2", "new-3"])

    chunks = list(document.chunks.order_by("order").values_list("text", "order"))
    assert chunks == [("new-1", 0), ("new-2", 1), ("new-3", 2)]
    assert document.chunks.count() == 3
