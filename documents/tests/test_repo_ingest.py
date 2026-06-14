from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse


@pytest.mark.django_db
def test_repo_ingest_enqueues_task(client, user, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    client.login(username="tester", password="pass1234")

    with patch("documents.views.ingest_repo_task.delay") as delay:
        response = client.post(
            reverse("documents:repo_ingest"),
            {"repo_full": "Tarik2012/RAG"},
            follow=True,
        )

    assert response.status_code == 200
    delay.assert_called_once_with("Tarik2012", "RAG", user.id, None)
    messages = [message.message for message in get_messages(response.wsgi_request)]
    assert "Ingesta de Tarik2012/RAG iniciada. Los archivos iran apareciendo en la lista." in messages


@pytest.mark.django_db
def test_repo_ingest_rejects_invalid_format(client, user, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    client.login(username="tester", password="pass1234")

    with patch("documents.views.ingest_repo_task.delay") as delay:
        response = client.post(
            reverse("documents:repo_ingest"),
            {"repo_full": "Tarik2012"},
            follow=True,
        )

    assert response.status_code == 200
    delay.assert_not_called()
    messages = [message.message for message in get_messages(response.wsgi_request)]
    assert "Formato invalido. Usa owner/repo o la URL del repo, p. ej. Tarik2012/RAG." in messages
