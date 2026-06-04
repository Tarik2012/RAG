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


def test_retriever_orders_results_by_similarity(embedded_chunks):
    provider = TestEmbeddingProvider()
    retriever = Retriever(provider)
    document = embedded_chunks[0].document

    results = retriever.retrieve(query="alpha text", top_k=3, user=document.owner)

    assert results
    top_chunk, _ = results[0]
    assert top_chunk.text == "alpha text"

    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)


def test_retriever_only_returns_active_document_chunks(user):
    provider = TestEmbeddingProvider()
    vector = provider.embed_texts(["alpha text"])[0]

    active_doc = Document.objects.create(
        owner=user, original_name="active.txt",
        file=SimpleUploadedFile("active.txt", b"x"),
        content_type="text/plain", size=1,
        status="processed", is_active=True,
    )
    DocumentChunk.objects.create(
        document=active_doc, order=0, text="alpha text",
        embedding_status="embedded", embedding=vector,
        embedding_vector=vector, embedding_model="fake",
    )

    inactive_doc = Document.objects.create(
        owner=user, original_name="inactive.txt",
        file=SimpleUploadedFile("inactive.txt", b"y"),
        content_type="text/plain", size=1,
        status="processed", is_active=False,
    )
    DocumentChunk.objects.create(
        document=inactive_doc, order=0, text="alpha text",
        embedding_status="embedded", embedding=vector,
        embedding_vector=vector, embedding_model="fake",
    )

    retriever = Retriever(provider)
    results = retriever.retrieve(query="alpha text", top_k=10, user=user)

    assert results
    assert all(chunk.document_id == active_doc.id for chunk, _ in results)


class TestEmbeddingProvider:
    DIMENSION = 1536

    def embed_texts(self, texts):
        embeddings = []
        for text in texts:
            vector = [float((ord(c) % 10)) for c in text[: self.DIMENSION]]
            vector += [0.0] * (self.DIMENSION - len(vector))
            embeddings.append(vector)
        return embeddings


def test_retriever_merges_results_across_query_variants(document, user):
    provider = TestEmbeddingProvider()

    for i, text in enumerate(["alpha", "zulu"]):
        vec = provider.embed_texts([text])[0]
        DocumentChunk.objects.create(
            document=document, order=i, text=text,
            embedding_status="embedded", embedding=vec,
            embedding_vector=vec, embedding_model="fake",
        )

    class FakeRewriter:
        def expand(self, question, n=3):
            return ["alpha", "zulu"]

    retriever = Retriever(provider, query_rewriter=FakeRewriter())
    results = retriever.retrieve(query="alpha", top_k=10, user=user)

    by_text = {chunk.text: score for chunk, score in results}
    assert "alpha" in by_text
    assert "zulu" in by_text
    assert by_text["alpha"] == pytest.approx(1.0, abs=1e-6)
    assert by_text["zulu"] == pytest.approx(1.0, abs=1e-6)
