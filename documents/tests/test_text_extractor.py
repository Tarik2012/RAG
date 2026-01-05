import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from documents.models import Document
from documents.services.text_extractor import extract_text_from_document


class TextExtractorTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.user = get_user_model().objects.create_user(
            username="tester",
            password="pass1234",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_document(self, content_type="application/pdf"):
        uploaded = SimpleUploadedFile(
            "test.pdf",
            b"%PDF-1.4\n%EOF",
            content_type=content_type,
        )
        with self.settings(MEDIA_ROOT=self.temp_dir):
            return Document.objects.create(
                owner=self.user,
                original_name="test.pdf",
                file=uploaded,
                content_type=content_type,
                size=uploaded.size,
                status="uploaded",
            )

    def test_pdf_happy_path_returns_extracted_text(self):
        document = self._create_document("application/pdf")
        with patch(
            "documents.services.text_extractor._extract_text_from_pdf",
            return_value="hello world",
        ) as mock_extract:
            result = extract_text_from_document(document)

        self.assertEqual(result, "hello world")
        mock_extract.assert_called_once_with(document.file.path)

    def test_pdf_empty_extraction_returns_empty_string(self):
        document = self._create_document("application/pdf")
        with patch(
            "documents.services.text_extractor._extract_text_from_pdf",
            return_value="",
        ):
            result = extract_text_from_document(document)

        self.assertEqual(result, "")

    def test_unsupported_content_type_returns_empty_string(self):
        document = self._create_document("text/plain")
        result = extract_text_from_document(document)

        self.assertEqual(result, "")