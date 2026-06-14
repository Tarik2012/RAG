import pytest

from documents.services.chunker import chunk_text


def test_chunking_splits_long_text_into_bounded_chunks():
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = chunk_text(text, chunk_size=10, chunk_overlap=0)

    assert len(chunks) > 1
    assert all(c for c in chunks)
    assert all(len(c) <= 10 for c in chunks)
    assert "".join(chunks) == text


def test_overlap_duplicates_content_between_chunks():
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = chunk_text(text, chunk_size=10, chunk_overlap=4)

    assert len(chunks) > 1
    assert len("".join(chunks)) > len(text)


def test_overlap_greater_than_chunk_size_raises_value_error():
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=5, chunk_overlap=6)
