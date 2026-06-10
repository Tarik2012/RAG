from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document
from documents.tasks import process_document_task


@pytest.mark.django_db(transaction=True)
def test_failed_status_persists_after_task_rollback(user):
    uploaded = SimpleUploadedFile(
        "test.pdf",
        b"%PDF-1.4\n%EOF",
        content_type="application/pdf",
    )
    document = Document.objects.create(
        owner=user,
        original_name="test.pdf",
        file=uploaded,
        content_type="application/pdf",
        size=uploaded.size,
        status="uploaded",
    )

    with patch("documents.tasks.process_document", side_effect=RuntimeError("boom")):
        try:
            process_document_task(document.id)
        except RuntimeError:
            pass

    document.refresh_from_db()
    assert document.status == "failed"


@pytest.mark.django_db(transaction=True)
def test_activation_failure_does_not_mark_document_failed(document_factory):
    doc = document_factory()

    def fake_process(document):
        document.status = "processed"
        document.save(update_fields=["status"])
        return 1

    with (
        patch("documents.tasks.process_document", new=fake_process),
        patch("documents.models.Document.set_active_for_user", side_effect=Exception("boom")),
    ):
        process_document_task.apply(args=[doc.id])

    doc.refresh_from_db()
    assert doc.status == "processed"
    assert doc.is_active is False
