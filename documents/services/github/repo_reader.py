import base64
import os
import requests

# Carpetas que NO se ingieren (dependencias, generados, control de versiones)
SKIP_DIRS = {
    "node_modules", ".git", "venv", ".venv", "env", "dist", "build",
    "__pycache__", ".next", "target", "vendor", ".pytest_cache",
}

# Extensiones binarias/generadas que NO se ingieren
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".pdf",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".lock", ".pyc", ".pyo",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp4", ".mp3", ".mov",
    ".exe", ".so", ".dll", ".bin", ".jar", ".class", ".o", ".a",
    ".db", ".sqlite3", ".map",
}

# Archivos concretos que NO se ingieren (lockfiles, basura del SO)
SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock", ".DS_Store",
}

MAX_FILES = 300
MAX_FILE_BYTES = 200000


def list_repo_code_files(owner: str, repo: str) -> list[str]:
    """Lista las rutas de un repo de GitHub: trae todo el texto (código, config, docs)
    y salta binarios, dependencias y generados."""
    pat = os.environ.get("GITHUB_PAT", "")
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }

    # 1. rama por defecto
    r = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=headers, timeout=30,
    )
    r.raise_for_status()
    branch = r.json()["default_branch"]

    # 2. árbol completo (recursivo)
    r = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
        headers=headers, timeout=30,
    )
    r.raise_for_status()
    tree = r.json().get("tree", [])

    # 3. traer todo menos basura
    files = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = item["path"]
        if any(part in SKIP_DIRS for part in path.split("/")):
            continue
        name = os.path.basename(path)
        if name in SKIP_FILENAMES:
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext in SKIP_EXTENSIONS:
            continue
        if item.get("size", 0) > MAX_FILE_BYTES:
            continue
        files.append(path)

    return files[:MAX_FILES]


def fetch_file_content(owner: str, repo: str, path: str) -> str:
    """Devuelve el contenido de texto de un archivo del repo."""
    pat = os.environ.get("GITHUB_PAT", "")
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }
    r = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
        headers=headers, timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
