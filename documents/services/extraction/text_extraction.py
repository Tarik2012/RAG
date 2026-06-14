def get_document_full_text(document) -> str:
    stored_file = getattr(document, "file", None)
    if stored_file:
        try:
            stored_file.open("rb")
            try:
                stored_file.seek(0)
                file_text = stored_file.read().decode("utf-8", errors="ignore")
            finally:
                stored_file.close()
            if file_text.strip():
                return file_text
        except (FileNotFoundError, OSError):
            pass  # archivo no disponible -> usar fallback de chunks

    # Last resort only: reconstruct from chunks if the original file is unavailable.
    chunks = document.chunks.order_by("order").values_list("text", flat=True)
    return "\n\n".join(chunk for chunk in chunks if chunk)
