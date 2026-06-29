import json
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def _build_opengrep_command(target: str) -> list[str]:
    return [
        "opengrep", "scan",
        "--config", "p/default",
        "--config", "p/security-audit",
        "--json", "--quiet",
        target,
    ]


def is_analyzable_file(original_name: str, content_type: str = "") -> bool:
    """Por ahora solo Python, alineado con el analisis estatico actual."""
    name = original_name or ""
    return name.endswith(".py") or "python" in (content_type or "").lower()


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


def scan_directory(tmp_root: str, timeout: int = 600) -> dict:
    """Ejecuta opengrep una vez sobre un directorio entero.

    Devuelve el JSON parseado de opengrep (results/errors) o un error global estructurado.
    Es mucho mas rapido que escanear archivo por archivo porque carga las reglas una sola vez.
    """
    cmd = _build_opengrep_command(tmp_root)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"results": [], "errors": [{"message": f"opengrep timeout tras {timeout}s"}]}
    except Exception as exc:
        return {"results": [], "errors": [{"message": f"opengrep fallo: {exc}"}]}

    if proc.returncode not in (0, 1):
        return {
            "results": [],
            "errors": [
                {"message": f"opengrep returncode {proc.returncode}: {proc.stderr[:500]}"}
            ],
        }

    if not proc.stdout.strip():
        return {"results": [], "errors": []}

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"results": [], "errors": [{"message": f"JSON invalido de opengrep: {exc}"}]}

    return {"results": data.get("results", []), "errors": data.get("errors", [])}


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
            _build_opengrep_command(tmp_path),
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
