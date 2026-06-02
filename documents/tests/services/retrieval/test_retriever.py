import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
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
        status="processed",
        is_active=True,
    )


@pytest.fixture
def embedded_chunks(document):
    chunks = []
    texts = ["alpha text", "bravo text", "charlie text"]
    embeddings = TestEmbeddingProvider().embed_texts(texts)

    for i, (text, vector) in enumerate(zip(texts, embeddings)):
        chunk = DocumentChunk.objects.create(
            document=document,
            order=i,
            text=text,
            embedding_status="embedded",
            embedding=vector,
            embedding_vector=vector,
            embedding_model="fake",
        )
        chunks.append(chunk)

    return chunks


def test_retriever_returns_top_k_chunks(embedded_chunks):
    provider = TestEmbeddingProvider()
    retriever = Retriever(provider)

    document = embedded_chunks[0].document
    results = retriever.retrieve(query="alpha", top_k=2, user=document.owner)

    assert len(results) == 2
    assert all(isinstance(score, float) for _, score in results)
class TestEmbeddingProvider:
    DIMENSION = 1536

    def embed_texts(self, texts):
        embeddings = []
        for text in texts:
            vector = [float((ord(c) % 10)) for c in text[: self.DIMENSION]]
            vector += [0.0] * (self.DIMENSION - len(vector))
            embeddings.append(vector)
        return embeddings
