import json
import pytest

from django.urls import reverse


pytestmark = pytest.mark.django_db


def test_ask_view_returns_200(client):
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
