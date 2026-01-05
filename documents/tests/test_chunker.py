from django.test import TestCase

from documents.services.chunker import chunk_text


class ChunkerTests(TestCase):
    def test_basic_chunking_no_overlap(self):
        text = "abcdefghijklmnopqrstuvwxyz"
        chunks = chunk_text(text, chunk_size=10, overlap=0)

        self.assertEqual(
            chunks,
            [
                "abcdefghij",
                "klmnopqrst",
                "uvwxyz",
            ],
        )

    def test_overlap_behavior(self):
        text = "abcdefghij"
        chunks = chunk_text(text, chunk_size=6, overlap=2)

        self.assertEqual(chunks, ["abcdef", "efghij", "ij"])