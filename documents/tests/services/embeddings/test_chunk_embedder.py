import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
from documents.services.embeddings.chunk_embedder import ChunkEmbedder


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


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="test-user",
        email="test-user@example.com",
        password="password123",
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
def chunks(document):
    texts = ["alpha", "bravo", "charlie"]
    created = []
    for index, text in enumerate(texts, start=1):
        created.append(
            DocumentChunk.objects.create(
                document=document,
                order=index,
                text=text,
            )
        )
    return created


@pytest.fixture
def model_name():
    return "fake-model-v1"


@pytest.fixture
def embedder(model_name):
    provider = TestEmbeddingProvider()
    return ChunkEmbedder(provider, model_name=model_name)


@pytest.fixture
def embedded_chunks(chunks, embedder):
    embedder.embed_chunks(chunks)
    ids = [chunk.id for chunk in chunks]
    return list(DocumentChunk.objects.filter(id__in=ids).order_by("order"))


def test_embedder_saves_embeddings_for_multiple_chunks(embedded_chunks):
    provider = TestEmbeddingProvider()
    expected = provider.embed_texts([chunk.text for chunk in embedded_chunks])

    assert [chunk.embedding for chunk in embedded_chunks] == expected


def test_embedder_sets_embedding_status_to_embedded(embedded_chunks):
    assert {chunk.embedding_status for chunk in embedded_chunks} == {"embedded"}


def test_embedder_sets_embedding_model(embedded_chunks, model_name):
    assert {chunk.embedding_model for chunk in embedded_chunks} == {model_name}


def test_embedder_sets_embedded_at(embedded_chunks):
    assert all(chunk.embedded_at is not None for chunk in embedded_chunks)


def test_embedder_uses_expected_embedding_dimension(embedded_chunks):
    assert all(
        len(chunk.embedding) == TestEmbeddingProvider.DIMENSION
        for chunk in embedded_chunks
    )


def test_embedder_noops_on_empty_list(embedder, chunks):
    embedder.embed_chunks([])

    chunk = DocumentChunk.objects.get(id=chunks[0].id)
    assert chunk.embedding_status == "pending"
    assert chunk.embedding is None
    assert chunk.embedding_model is None
    assert chunk.embedded_at is None


def test_embedder_raises_on_invalid_embedding_count(chunks, model_name):
    class BadFakeEmbeddingProvider(TestEmbeddingProvider):
        def embed_texts(self, texts):
            embeddings = super().embed_texts(texts)
            return embeddings[:-1]

    embedder = ChunkEmbedder(BadFakeEmbeddingProvider(), model_name=model_name)

    with pytest.raises(ValueError, match="invalid number of embeddings"):
        embedder.embed_chunks(chunks)
