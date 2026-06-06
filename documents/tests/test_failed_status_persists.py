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
