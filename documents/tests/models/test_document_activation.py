import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.utils import IntegrityError

from documents.models import Document


def create_document(
    *,
    owner,
    name,
    status,
    is_active=False,
    content_type="application/pdf",
):
    uploaded = SimpleUploadedFile(
        name,
        b"%PDF-1.4\n%EOF",
        content_type=content_type,
    )
    return Document.objects.create(
        owner=owner,
        original_name=name,
        file=uploaded,
        content_type=content_type,
        size=uploaded.size,
        status=status,
        is_active=is_active,
    )


@pytest.mark.django_db
def test_only_one_active_document_per_user(user, media_root):
    doc_one = create_document(owner=user, name="one.pdf", status="processed")
    doc_two = create_document(owner=user, name="two.pdf", status="processed")

    Document.set_active_for_user(document=doc_one)
    Document.set_active_for_user(document=doc_two)

    active_docs = Document.objects.filter(owner=user, is_active=True)
    assert active_docs.count() == 1
    assert active_docs.first().id == doc_two.id


@pytest.mark.django_db
def test_cannot_activate_unprocessed_document(user, media_root):
    document = create_document(owner=user, name="draft.pdf", status="uploaded")

    with pytest.raises(ValueError):
        Document.set_active_for_user(document=document)


@pytest.mark.django_db
def test_database_constraint_enforcement(user, media_root):
    create_document(
        owner=user,
        name="active-one.pdf",
        status="processed",
        is_active=True,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            create_document(
                owner=user,
                name="active-two.pdf",
                status="processed",
                is_active=True,
            )
