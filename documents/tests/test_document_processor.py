import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from documents.models import Document, DocumentChunk
from documents.services.document_processor import process_document


class DocumentProcessorTests(TestCase):
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

    def test_process_document_creates_chunks_and_returns_count(self):
        document = self._create_document()
        sample_text = "Hello world. This is a small document."

        with patch(
            "documents.services.document_processor.extract_text_from_document",
            return_value=sample_text,
        ):
            count = process_document(document)

        self.assertEqual(count, 1)
        self.assertEqual(DocumentChunk.objects.filter(document=document).count(), 1)
        self.assertEqual(document.chunks.first().text, sample_text)