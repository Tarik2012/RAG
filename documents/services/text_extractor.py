from pypdf import PdfReader


def extract_text_from_document(document) -> str:
    """
    Extrae texto de un documento segun su tipo.
    Actualmente soporta PDF.
    """

    content_type = (document.content_type or "").lower()

    if "pdf" in content_type:
        return _extract_text_from_pdf(document.file.path)

    # Tipos no soportados todavia
    return ""


def _extract_text_from_pdf(file_path: str) -> str:
    """
    Extrae texto de un archivo PDF usando pypdf.
    """
    reader = PdfReader(file_path)
    pages_text = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)

    return "\n".join(pages_text)
