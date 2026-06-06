import pytest
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document
from documents.services.text_extractor import extract_text_from_document


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
    def _create_document(content_type="application/pdf"):
        uploaded = SimpleUploadedFile(
            "test.pdf",
            b"%PDF-1.4\n%EOF",
            content_type=content_type,
        )
        return Document.objects.create(
            owner=user,
            original_name="test.pdf",
            file=uploaded,
            content_type=content_type,
            size=uploaded.size,
            status="uploaded",
        )

    return _create_document


def test_pdf_happy_path_returns_extracted_text(document_factory):
    document = document_factory("application/pdf")

    with patch(
        "documents.services.text_extractor._extract_text_from_pdf",
        return_value="hello world",
    ) as mock_extract:
        result = extract_text_from_document(document)

    assert result == "hello world"
    mock_extract.assert_called_once_with(document.file)


def test_pdf_empty_extraction_returns_empty_string(document_factory):
    document = document_factory("application/pdf")

    with patch(
        "documents.services.text_extractor._extract_text_from_pdf",
        return_value="",
    ):
        result = extract_text_from_document(document)

    assert result == ""


def test_unsupported_content_type_returns_empty_string(document_factory):
    document = document_factory("text/plain")

    result = extract_text_from_document(document)

    assert result == ""


def test_unsupported_content_type_does_not_call_pdf_extractor(document_factory):
    document = document_factory("text/plain")

    with patch("documents.services.text_extractor._extract_text_from_pdf") as mock_extract:
        result = extract_text_from_document(document)

    assert result == ""
    mock_extract.assert_not_called()
