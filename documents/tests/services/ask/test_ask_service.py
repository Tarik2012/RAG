import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
from documents.services.embeddings.embedding_provider import FakeEmbeddingProvider
from documents.services.retrieval.retriever import Retriever
from documents.services.ask.ask_service import AskService
from documents.services.llm.fake_llm_provider import FakeLLMProvider


pytestmark = pytest.mark.django_db


@pytest.fixture
def document(user):
    file = SimpleUploadedFile("doc.txt", b"hello")
    return Document.objects.create(
        owner=user,
        original_name="doc.txt",
        file=file,
        content_type="text/plain",
        size=5,
    )


@pytest.fixture
def embedded_chunks(document):
    texts = ["alpha text", "bravo text"]
    for i, text in enumerate(texts):
        DocumentChunk.objects.create(
            document=document,
            order=i,
            text=text,
            embedding_status="embedded",
            embedding=[1.0] * FakeEmbeddingProvider.DIMENSION,
            embedding_model="fake",
        )


def test_ask_service_returns_answer_and_context(embedded_chunks):
    retriever = Retriever(FakeEmbeddingProvider())
    llm = FakeLLMProvider()

    ask_service = AskService(
        retriever=retriever,
        llm_provider=llm,
    )

    result = ask_service.ask(question="alpha")

    assert "answer" in result
    assert result["answer"].startswith("FAKE ANSWER")
    assert "context" in result
    assert "alpha text" in result["context"]
