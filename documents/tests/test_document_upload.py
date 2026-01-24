from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documents.models import Document


@pytest.mark.django_db
def test_document_upload_enqueues_task(client, user, settings, media_root):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    client.login(username="tester", password="pass1234")

    upload = SimpleUploadedFile(
        "test.pdf",
        b"%PDF-1.4\n%EOF",
        content_type="application/pdf",
    )

    with patch("documents.views.process_document_task.delay") as delay:
        response = client.post(
            reverse("documents:upload"),
            {"original_name": "test.pdf", "file": upload},
        )

    assert response.status_code == 302
    delay.assert_called_once()

    doc_id = delay.call_args.args[0]
    assert Document.objects.filter(id=doc_id).exists()


@pytest.mark.django_db
def test_document_upload_does_not_call_sync_processing(client, user, settings, media_root):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    client.login(username="tester", password="pass1234")

    upload = SimpleUploadedFile(
        "test.pdf",
        b"%PDF-1.4\n%EOF",
        content_type="application/pdf",
    )

    with (
        patch("documents.views.process_document_task.delay") as delay,
        patch("documents.services.document_processor.process_document") as process_document,
    ):
        response = client.post(
            reverse("documents:upload"),
            {"original_name": "test.pdf", "file": upload},
        )

    assert response.status_code == 302
    delay.assert_called_once()
    process_document.assert_not_called()
