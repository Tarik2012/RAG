import pytest
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
from documents.services.document_processor import process_document


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


def test_process_document_creates_chunks_and_returns_count(document_factory):
    document = document_factory()
    sample_text = "Hello world. This is a small document."

    with patch(
        "documents.services.document_processor.extract_text_from_document",
        return_value=sample_text,
    ):
        count = process_document(document)

    assert count == 1
    assert DocumentChunk.objects.filter(document=document).count() == 1
    assert document.chunks.first().text == sample_text


def test_process_document_marks_failed_on_empty_text(document_factory):
    document = document_factory()

    with patch(
        "documents.services.document_processor.extract_text_from_document",
        return_value="",
    ):
        with pytest.raises(ValueError):
            process_document(document)

    document.refresh_from_db()
    assert document.status == "failed"
    assert DocumentChunk.objects.filter(document=document).count() == 0
