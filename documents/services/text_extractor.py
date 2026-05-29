from pypdf import PdfReader
import csv
from pathlib import Path


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
    file_path = Path(document.file.path)

    if content_type.startswith("application/pdf"):
        return _extract_text_from_pdf(file_path)

    if content_type.startswith("text/csv") or file_path.suffix.lower() == ".csv":
        return _extract_text_from_csv(file_path)

    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".java", ".cs", ".cpp", ".go", ".rb",
        ".php", ".swift", ".kt", ".html", ".htm", ".css",
        ".json", ".xml", ".yaml", ".yml", ".md", ".txt", ".rst"
    }
    if file_path.suffix.lower() in CODE_EXTENSIONS:
        return _extract_text_from_code(file_path)

    # Tipo no soportado
    return ""


def _extract_text_from_pdf(file_path: Path) -> str:
    """
    Extrae texto de un PDF con capa de texto.
    No realiza OCR.
    """

    reader = PdfReader(str(file_path))
    pages_text: list[str] = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            cleaned = _normalize_text(text)
            if cleaned:
                pages_text.append(cleaned)

    return "\n".join(pages_text)


def _extract_text_from_csv(file_path: Path) -> str:
    """
    Convierte un CSV en texto narrativo embeddable.

    Cada fila se transforma en una frase tipo:
    "ColumnA: valueA. ColumnB: valueB."
    """

    rows_text: list[str] = []

    with open(file_path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)

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


def _extract_text_from_code(file_path: Path) -> str:
    with open(file_path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def _normalize_text(text: str) -> str:
    """
    Limpia texto para embeddings:
    - colapsa espacios
    - elimina líneas vacías
    """

    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    return " ".join(lines)
