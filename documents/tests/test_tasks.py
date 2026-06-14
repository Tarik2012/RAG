from unittest.mock import Mock

import pytest
from celery.exceptions import Retry
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document
from documents.tasks import process_document_task
from documents import tasks


pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="task-tester",
        password="pass1234",
    )


@pytest.fixture
def document_factory(user):
    def _create_document(*, status="uploaded"):
        uploaded = SimpleUploadedFile(
            "test.pdf",
            b"%PDF-1.4\n%EOF",
            content_type="application/pdf",
        )
        return Document.objects.create(
            owner=user,
            original_name="test.pdf",
            file=uploaded,
            content_type="application/pdf",
            size=uploaded.size,
            status=status,
        )

    return _create_document


def test_process_document_task_skips_already_processed_documents(monkeypatch, document_factory):
    document = document_factory(status="processed")
    process_document = Mock()

    monkeypatch.setattr(tasks, "process_document", process_document)

    process_document_task.run(document.id)

    process_document.assert_not_called()


def test_process_document_task_retries_on_failure(monkeypatch, document_factory):
    document = document_factory()
    retry_calls = []

    def raise_error(_document):
        raise RuntimeError("temporary failure")

    def fake_retry(*args, **kwargs):
        retry_calls.append(kwargs)
        raise Retry()

    monkeypatch.setattr(tasks, "process_document", raise_error)
    monkeypatch.setattr(process_document_task, "retry", fake_retry)

    with pytest.raises(Retry):
        process_document_task.run(document.id)

    assert len(retry_calls) == 1
    assert isinstance(retry_calls[0]["exc"], RuntimeError)
    assert retry_calls[0]["countdown"] >= 0
