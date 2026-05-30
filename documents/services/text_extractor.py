from io import TextIOWrapper
from pathlib import Path
import csv

from pypdf import PdfReader


def extract_text_from_document(document) -> str:
    """
    Extrae texto de un documento según su tipo.

    Soporta:
    - PDF (application/pdf)
    - CSV (text/csv) → normalizado a texto narrativo

    Devuelve string vacío si el tipo no es soportado
    o si no se puede extraer texto semánticamente útil.
    """

    content_type = (document.content_type or "").lower()
    file_name = Path(document.file.name or "")

    if content_type.startswith("application/pdf"):
        return _extract_text_from_pdf(document.file)

    if content_type.startswith("text/csv") or file_name.suffix.lower() == ".csv":
        return _extract_text_from_csv(document.file)

    code_extensions = {
        ".py", ".js", ".ts", ".java", ".cs", ".cpp", ".go", ".rb",
        ".php", ".swift", ".kt", ".html", ".htm", ".css",
        ".json", ".xml", ".yaml", ".yml", ".md", ".txt", ".rst",
    }
    if file_name.suffix.lower() in code_extensions:
        return _extract_text_from_code(document.file)

    # Tipo no soportado
    return ""


def _extract_text_from_pdf(file_obj) -> str:
    """
    Extrae texto de un PDF con capa de texto.
    No realiza OCR.
    """

    file_obj.open("rb")
    try:
        file_obj.seek(0)
        reader = PdfReader(file_obj)
        pages_text: list[str] = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                cleaned = _normalize_text(text)
                if cleaned:
                    pages_text.append(cleaned)

        return "\n".join(pages_text)
    finally:
        file_obj.close()


def _extract_text_from_csv(file_obj) -> str:
    """
    Convierte un CSV en texto narrativo embeddable.

    Cada fila se transforma en una frase tipo:
    "ColumnA: valueA. ColumnB: valueB."
    """

    rows_text: list[str] = []
    text_stream = None

    file_obj.open("rb")
    try:
        file_obj.seek(0)
        text_stream = TextIOWrapper(file_obj, encoding="utf-8", errors="ignore", newline="")
        reader = csv.DictReader(text_stream)

        if not reader.fieldnames:
            return ""

        for row in reader:
            parts: list[str] = []

            for key, value in row.items():
                if not key:
                    continue

                value = (value or "").strip()
                if not value:
                    continue

                key = key.strip()
                parts.append(f"{key}: {value}")

            if parts:
                sentence = ". ".join(parts) + "."
                rows_text.append(sentence)

        return "\n".join(rows_text)
    finally:
        if text_stream is not None:
            text_stream.detach()
        file_obj.close()


def _extract_text_from_code(file_obj) -> str:
    file_obj.open("rb")
    try:
        file_obj.seek(0)
        return file_obj.read().decode("utf-8", errors="ignore")
    finally:
        file_obj.close()


def _normalize_text(text: str) -> str:
    """
    Limpia texto para embeddings:
    - colapsa espacios
    - elimina líneas vacías
    """

    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    return " ".join(lines)
