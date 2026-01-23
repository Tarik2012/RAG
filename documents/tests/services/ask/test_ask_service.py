import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
from documents.services.retrieval.retriever import Retriever
from documents.services.ask.ask_service import AskService
from documents.services.llm.llm_provider import LLMProvider


pytestmark = pytest.mark.django_db


class TestEmbeddingProvider:
    DIMENSION = 8

    def embed_texts(self, texts):
        embeddings = []
        for text in texts:
            vector = [float((ord(c) % 10)) for c in text[: self.DIMENSION]]
            vector += [0.0] * (self.DIMENSION - len(vector))
            embeddings.append(vector)
        return embeddings


class TestLLMProvider(LLMProvider):
    def generate(self, *, question: str, context: str) -> str:
        return (
            "FAKE ANSWER\n"
            f"QUESTION: {question}\n"
            f"CONTEXT: {context[:200]}"
        )


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
            embedding=[1.0] * TestEmbeddingProvider.DIMENSION,
            embedding_model="fake",
        )


def test_ask_service_returns_answer_and_context(embedded_chunks):
    retriever = Retriever(TestEmbeddingProvider())
    llm = TestLLMProvider()

    ask_service = AskService(
        retriever=retriever,
        llm_provider=llm,
    )

    result = ask_service.ask(question="alpha")

    assert "answer" in result
    assert result["answer"].startswith("FAKE ANSWER")
    assert "context" in result
    assert "alpha text" in result["context"]
