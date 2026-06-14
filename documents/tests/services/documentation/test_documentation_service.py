import pytest

from documents.models import Document, DocumentChunk
from documents.services.documentation import DocumentationService


pytestmark = pytest.mark.django_db


class FakeLLMProvider:
    def complete(self, *, instructions, input):
        return "DOCUMENTACION DE PRUEBA"


@pytest.fixture
def owner(user):
    return user


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(
        username="other-user",
        password="pass1234",
    )


@pytest.fixture
def service():
    return DocumentationService(llm_provider=FakeLLMProvider())


def test_generate_returns_documentation_for_processed_document_with_chunks(owner, service):
    document = Document.objects.create(
        owner=owner,
        original_name="sample.py",
        file="documents/sample.py",
        content_type="text/plain",
        size=42,
        status="processed",
    )
    DocumentChunk.objects.create(document=document, order=0, text="def first():\n    pass")
    DocumentChunk.objects.create(document=document, order=1, text="class Second:\n    pass")

    result = service.generate(document_id=document.id, user=owner)

    assert result["documentation"] == "DOCUMENTACION DE PRUEBA"
    assert result["document_id"] == document.id
    assert result["document_name"] == "sample.py"


def test_generate_returns_error_for_missing_document(owner, service):
    result = service.generate(document_id=999999, user=owner)

    assert "error" in result


def test_generate_returns_error_for_wrong_owner(owner, other_user, service):
    document = Document.objects.create(
        owner=other_user,
        original_name="private.py",
        file="documents/private.py",
        content_type="text/plain",
        size=24,
        status="processed",
    )

    result = service.generate(document_id=document.id, user=owner)

    assert "error" in result


def test_generate_returns_error_when_document_has_no_readable_content(owner, service):
    document = Document.objects.create(
        owner=owner,
        original_name="empty.py",
        file="documents/empty.py",
        content_type="text/plain",
        size=0,
        status="processed",
    )

    result = service.generate(document_id=document.id, user=owner)

    assert "error" in result
