import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document


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
