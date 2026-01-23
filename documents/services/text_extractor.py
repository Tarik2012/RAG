from pypdf import PdfReader
import csv


def extract_text_from_document(document) -> str:
    """
    Extrae texto de un documento según su tipo.
    Soporta PDF, TXT y CSV.
    """

    content_type = (document.content_type or "").lower()
    file_path = document.file.path

    if content_type.startswith("application/pdf"):
        return _extract_text_from_pdf(file_path)

    # Tipo no soportado
    return ""


def _extract_text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages_text = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)

    return "\n".join(pages_text)


def _extract_text_from_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _extract_text_from_csv(file_path: str) -> str:
    rows = []

    with open(file_path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(" | ".join(row))

    return "\n".join(rows)
