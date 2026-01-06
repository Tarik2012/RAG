import pytest

from documents.services.chunker import chunk_text


def test_basic_chunking_no_overlap():
    text = "abcdefghijklmnopqrstuvwxyz"

    chunks = chunk_text(text, chunk_size=10, overlap=0)

    assert chunks == [
        "abcdefghij",
        "klmnopqrst",
        "uvwxyz",
    ]


def test_overlap_behavior():
    text = "abcdefghij"

    chunks = chunk_text(text, chunk_size=6, overlap=2)

    assert chunks == ["abcdef", "efghij", "ij"]


def test_invalid_overlap_raises_value_error():
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=5, overlap=5)
