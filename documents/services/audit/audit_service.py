import logging
import os
import tempfile

from documents.models import Document
from documents.services.agent.static_analysis import (
    is_analyzable_file,
    resolve_language_suffix,
    scan_directory,
)
from documents.services.extraction.text_extraction import get_document_full_text

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 2_000_000


def _is_analyzable(document) -> bool:
    return is_analyzable_file(document.original_name, document.content_type)


def _safe_staged_name(document) -> str:
    """Nombre staged seguro y unico por documento."""
    base = os.path.basename(document.original_name or f"doc_{document.id}")
    base = base.replace("\\", "_").replace("/", "_") or f"doc_{document.id}"
    suffix = resolve_language_suffix(document.original_name, document.content_type)
    if suffix and not base.endswith(suffix):
        base = os.path.splitext(base)[0] + suffix
    return f"{document.id}/{base}"


def audit_project(user, project) -> dict:
    """Escanea todos los archivos analizables de un proyecto en un solo pase de opengrep."""
    docs = Document.objects.filter(
        owner=user, status="processed", project=project
    ).order_by("id")

    scanned = 0
    skipped = 0
    errors = []
    manifest = {}

    with tempfile.TemporaryDirectory() as tmp_root:
        for doc in docs:
            if not _is_analyzable(doc):
                skipped += 1
                continue
            code = get_document_full_text(doc)
            if not code.strip():
                skipped += 1
                continue
            if len(code.encode("utf-8")) > MAX_FILE_BYTES:
                skipped += 1
                errors.append({"file": doc.original_name, "error": "archivo demasiado grande, omitido"})
                continue

            rel_path = _safe_staged_name(doc)
            abs_path = os.path.join(tmp_root, rel_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as fh:
                fh.write(code)
            manifest[rel_path] = {"original_name": doc.original_name}
            scanned += 1

        if scanned == 0:
            return {
                "project": project.name,
                "scanned": 0,
                "skipped": skipped,
                "files_with_findings": [],
                "clean_files": 0,
                "total_findings": 0,
                "errors": errors,
            }

        scan_result = scan_directory(tmp_root)
        errors.extend(scan_result.get("errors", []))

        by_file = {}
        for r in scan_result.get("results", []):
            abs_p = r.get("path", "")
            rel_p = os.path.relpath(abs_p, tmp_root)
            info = manifest.get(rel_p)
            if not info:
                continue
            name = info["original_name"]
            by_file.setdefault(name, []).append(
                {
                    "rule": r.get("check_id", "unknown-rule"),
                    "line": r.get("start", {}).get("line"),
                    "severity": r.get("extra", {}).get("severity", ""),
                    "message": (r.get("extra", {}).get("message", "") or "").strip(),
                }
            )

    files_with_findings = []
    total_findings = 0
    for name, findings in by_file.items():
        files_with_findings.append(
            {
                "file": name,
                "count": len(findings),
                "findings": findings[:25],
            }
        )
        total_findings += len(findings)

    return {
        "project": project.name,
        "scanned": scanned,
        "skipped": skipped,
        "files_with_findings": files_with_findings,
        "clean_files": scanned - len(files_with_findings),
        "total_findings": total_findings,
        "errors": errors,
    }
