import json
import pytest

from django.urls import reverse
import documents.views as views


pytestmark = pytest.mark.django_db


class DummyEmbeddingProvider:
    def embed_texts(self, texts):
        return [[0.0] * 3 for _ in texts]


class DummyLLMProvider:
    def generate(self, *, question: str, context: str) -> str:
        return "stub answer"


class DummyQueryRewriter:
    def rewrite(self, question: str) -> str:
        return question


def test_ask_view_returns_200(client, monkeypatch):
    monkeypatch.setattr(views, "OpenAIEmbeddingProvider", DummyEmbeddingProvider)
    monkeypatch.setattr(views, "OpenAILLMProvider", DummyLLMProvider)
    monkeypatch.setattr(views, "QueryRewriter", DummyQueryRewriter)

    url = reverse("documents:ask")

    response = client.post(
        url,
        data=json.dumps({"question": "alpha"}),
        content_type="application/json",
    )

    assert response.status_code == 200

    data = response.json()
    assert "context" in data
    assert "question" in data


def test_ask_view_missing_question_returns_400(client):
    url = reverse("documents:ask")

    response = client.post(
        url,
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 400
