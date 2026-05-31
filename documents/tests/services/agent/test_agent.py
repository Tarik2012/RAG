import pytest

from documents.models import Document, DocumentChunk
from documents.services.agent.agent import _get_document_full_text


pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="agent-tester",
        password="pass1234",
    )


def test_get_document_full_text_concatenates_all_chunks_in_order(user):
    document = Document.objects.create(
        owner=user,
        original_name="sample.py",
        file="documents/sample.py",
        content_type="text/plain",
        size=42,
        status="processed",
        is_active=True,
    )

    DocumentChunk.objects.create(document=document, order=2, text="third()")
    DocumentChunk.objects.create(document=document, order=0, text="first()")
    DocumentChunk.objects.create(document=document, order=1, text="second()")

    assert _get_document_full_text(document) == "first()\n\nsecond()\n\nthird()"


def test_get_document_full_text_prefers_original_file_content(user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    file_path = tmp_path / "documents"
    file_path.mkdir()
    original_file = file_path / "sample.py"
    original_file.write_text("print('from file')\nprint('exact source')", encoding="utf-8")

    document = Document.objects.create(
        owner=user,
        original_name="sample.py",
        file="documents/sample.py",
        content_type="text/plain",
        size=original_file.stat().st_size,
        status="processed",
        is_active=True,
    )

    DocumentChunk.objects.create(document=document, order=0, text="print('chunk overlap')")
    DocumentChunk.objects.create(document=document, order=1, text="print('chunk overlap')")

    assert _get_document_full_text(document) == "print('from file')\nprint('exact source')"
