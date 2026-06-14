from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.forms import DocumentUploadForm


pytestmark = pytest.mark.django_db


def test_valid_pdf_is_accepted():
    uploaded = SimpleUploadedFile(
        "doc.pdf",
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n",
        content_type="application/pdf",
    )
    form = DocumentUploadForm(data={"original_name": "Test"}, files={"file": uploaded})

    assert form.is_valid() is True


def test_fake_pdf_is_rejected():
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    uploaded = SimpleUploadedFile("doc.pdf", png, content_type="application/pdf")
    form = DocumentUploadForm(data={"original_name": "Test"}, files={"file": uploaded})

    assert form.is_valid() is False
    assert "file" in form.errors


def test_valid_text_file_is_accepted():
    uploaded = SimpleUploadedFile(
        "notes.txt",
        b"hola mundo, esto es texto",
        content_type="text/plain",
    )
    form = DocumentUploadForm(data={"original_name": "Test"}, files={"file": uploaded})

    assert form.is_valid() is True


def test_oversized_file_is_rejected():
    with patch("documents.forms.MAX_UPLOAD_SIZE", 10):
        uploaded = SimpleUploadedFile(
            "notes.txt",
            b"12345678901",
            content_type="text/plain",
        )
        form = DocumentUploadForm(data={"original_name": "Test"}, files={"file": uploaded})

        assert form.is_valid() is False
        assert "file" in form.errors
