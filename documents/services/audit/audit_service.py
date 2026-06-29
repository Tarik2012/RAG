import logging

from documents.models import Document
from documents.services.agent.static_analysis import analyze_code, resolve_language_suffix
from documents.services.extraction.text_extraction import get_document_full_text

logger = logging.getLogger(__name__)


def _is_analyzable(document) -> bool:
    """Por ahora solo Python (igual que find_references)."""
    name = document.original_name or ""
    return name.endswith(".py") or "python" in (document.content_type or "").lower()


def audit_project(user, project) -> dict:
    """Escanea todos los archivos Python analizables de un proyecto con el escaner estatico.
    Determinista, sin LLM. Devuelve un dict con resumen y hallazgos por archivo.
    """
    docs = Document.objects.filter(owner=user, status="processed", project=project)

    scanned = 0
    skipped = 0
    files_with_findings = []
    total_findings = 0
    errors = []

    for doc in docs:
        if not _is_analyzable(doc):
            skipped += 1
            continue
        code = get_document_full_text(doc)
        if not code.strip():
            skipped += 1
            continue
        try:
            suffix = resolve_language_suffix(doc.original_name, doc.content_type)
            result = analyze_code(code, doc.original_name, suffix=suffix)
        except Exception as exc:
            logger.warning("audit: fallo escaneando %s: %s", doc.original_name, exc)
            errors.append({"file": doc.original_name, "error": str(exc)})
            continue

        scanned += 1
        results = result.get("results", [])
        if results:
            findings = []
            for r in results[:25]:
                findings.append(
                    {
                        "rule": r.get("check_id", "unknown-rule"),
                        "line": r.get("start", {}).get("line"),
                        "severity": r.get("extra", {}).get("severity", ""),
                        "message": (r.get("extra", {}).get("message", "") or "").strip(),
                    }
                )
            files_with_findings.append(
                {
                    "file": doc.original_name,
                    "count": len(results),
                    "findings": findings,
                }
            )
            total_findings += len(results)

    return {
        "project": project.name,
        "scanned": scanned,
        "skipped": skipped,
        "files_with_findings": files_with_findings,
        "clean_files": scanned - len(files_with_findings),
        "total_findings": total_findings,
        "errors": errors,
    }
