import json
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def resolve_language_suffix(original_name: str, content_type: str = "") -> str:
    """Determina la extension de lenguaje para el escaner. Usa la extension del nombre si existe;
    si no, infiere desde content_type. Cae a .txt si no se reconoce."""
    ext = os.path.splitext(original_name or "")[1]
    if ext:
        return ext
    ct = (content_type or "").lower()
    ct_map = {
        "text/x-python": ".py",
        "application/x-python": ".py",
        "text/x-python-script": ".py",
    }
    for key, suffix in ct_map.items():
        if key in ct:
            return suffix
    return ".txt"


def analyze_code(code: str, filename: str, suffix: str | None = None) -> dict:
    """Ejecuta semgrep (reglas de seguridad + bugs comunes, multi-lenguaje)
    sobre el codigo dado y devuelve los hallazgos reales en un dict,
    sin opinion del LLM."""
    if not suffix:
        suffix = resolve_language_suffix(filename)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    findings = {"results": [], "errors": []}

    try:
        result = subprocess.run(
            [
                "opengrep", "scan",
                "--config", "p/default",
                "--config", "p/security-audit",
                "--json", "--quiet",
                tmp_path,
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            findings["results"] = data.get("results", [])
        if result.returncode not in (0, 1):
            findings["errors"].append(result.stderr.strip()[:500])
    except Exception as exc:
        logger.warning("semgrep fallo al analizar %s: %s", filename, exc)
        findings["errors"].append(str(exc))
    finally:
        os.unlink(tmp_path)

    return findings
