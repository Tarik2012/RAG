import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
from documents.services.embeddings.embedding_provider import FakeEmbeddingProvider
from documents.services.retrieval.retriever import Retriever


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
    chunks = []
    texts = ["alpha text", "bravo text", "charlie text"]

    for i, text in enumerate(texts):
        chunk = DocumentChunk.objects.create(
            document=document,
            order=i,
            text=text,
            embedding_status="embedded",
            embedding=[float(i + 1)] * FakeEmbeddingProvider.DIMENSION,
            embedding_model="fake",
        )
        chunks.append(chunk)

    return chunks


def test_retriever_returns_top_k_chunks(embedded_chunks):
    provider = FakeEmbeddingProvider()
    retriever = Retriever(provider)

    results = retriever.retrieve(query="alpha", top_k=2)

    assert len(results) == 2
    assert all(isinstance(score, float) for _, score in results)
