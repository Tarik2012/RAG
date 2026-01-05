import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from documents.models import Document, DocumentChunk
from documents.services.chunk_persister import persist_chunks


class ChunkPersisterTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.user = get_user_model().objects.create_user(
            username="tester",
            password="pass1234",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_document(self):
        uploaded = SimpleUploadedFile(
            "test.pdf",
            b"%PDF-1.4\n%EOF",
            content_type="application/pdf",
        )
        with self.settings(MEDIA_ROOT=self.temp_dir):
            return Document.objects.create(
                owner=self.user,
                original_name="test.pdf",
                file=uploaded,
                content_type="application/pdf",
                size=uploaded.size,
                status="uploaded",
            )

    def test_persist_chunks_replaces_previous_chunks(self):
        document = self._create_document()

        DocumentChunk.objects.bulk_create(
            [
                DocumentChunk(document=document, order=0, text="old-1"),
                DocumentChunk(document=document, order=1, text="old-2"),
            ]
        )

        persist_chunks(document, ["new-1", "new-2", "new-3"])

        chunks = list(document.chunks.order_by("order").values_list("text", "order"))
        self.assertEqual(chunks, [("new-1", 0), ("new-2", 1), ("new-3", 2)])
        self.assertEqual(document.chunks.count(), 3)