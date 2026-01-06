import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
from documents.services.embeddings.chunk_embedder import ChunkEmbedder
from documents.services.embeddings.document_embedder import DocumentEmbedder
from documents.services.embeddings.embedding_provider import FakeEmbeddingProvider


pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="test-user",
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
    for index, text in enumerate(texts):
        created.append(
            DocumentChunk.objects.create(
                document=document,
                order=index,
                text=text,
            )
        )
    return created


def test_document_embedder_embeds_all_pending_chunks(document, chunks):
    provider = FakeEmbeddingProvider()
    chunk_embedder = ChunkEmbedder(provider, model_name="fake-model")
    document_embedder = DocumentEmbedder(chunk_embedder)

    processed = document_embedder.embed_document(document)

    assert processed == len(chunks)

    for chunk in DocumentChunk.objects.all():
        assert chunk.embedding_status == "embedded"
        assert chunk.embedding is not None
        assert chunk.embedding_model == "fake-model"
        assert chunk.embedded_at is not None


def test_document_embedder_returns_zero_when_no_pending_chunks(document, chunks):
    provider = FakeEmbeddingProvider()
    chunk_embedder = ChunkEmbedder(provider, model_name="fake-model")
    document_embedder = DocumentEmbedder(chunk_embedder)

    # Primera ejecución: embebe todo
    document_embedder.embed_document(document)

    # Segunda ejecución: ya no hay pendientes
    processed = document_embedder.embed_document(document)

    assert processed == 0
