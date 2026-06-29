import logging

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


def detect_project_audit(message: str) -> bool:
    """Detecta de forma determinista si el usuario pide auditar TODO el proyecto.
    Exige intencion (auditar/escanear/revisar seguridad) Y alcance global (todo el proyecto,
    repo entero, todos los archivos) en el mismo mensaje. Evita falsos positivos como
    '¿como funciona la auditoria?'."""
    if not message:
        return False
    text = message.lower()

    intent_terms = [
        "audita", "auditar", "auditoria", "auditoría",
        "escanea", "escanear", "scan",
        "revisa la seguridad", "revisar seguridad", "analiza la seguridad",
    ]
    scope_terms = [
        "todo el proyecto", "proyecto completo", "todo el repo", "repo entero",
        "repositorio completo", "todos los archivos", "todos los ficheros",
        "el proyecto entero", "toda la base de codigo", "todo el codigo",
    ]

    has_intent = any(t in text for t in intent_terms)
    has_scope = any(t in text for t in scope_terms)
    return has_intent and has_scope


def classify_message(message: str) -> str:
    """Clasifica un mensaje como 'chat' (charla casual) o 'agent' (pregunta real)."""
    if not settings.OPENAI_API_KEY:
        return "agent"
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model="gpt-4o-mini",
            temperature=0,
            instructions=(
                "You classify a user message for a code/document assistant. "
                "Reply with ONLY one word: chat or agent.\n"
                "Reply 'chat' ONLY if the message is a pure greeting, thanks, or acknowledgement "
                "with no task and no topic, like: 'hola', 'gracias', 'ok', 'perfecto', 'buenas', 'adios'.\n"
                "Reply 'agent' for EVERYTHING else: any question, any instruction or task "
                "(e.g. 'analiza views.py', 'vamos a trabajar con el repo X', 'que hace este archivo', "
                "'resume el codigo'), or anything mentioning files, code, repos, or documents. "
                "When in doubt, reply 'agent'."
            ),
            input=(message or "").strip(),
        )
        intent = (response.output_text or "").strip().lower()
        if intent in {"chat", "agent"}:
            return intent
        return "agent"
    except Exception:
        logger.exception("Message router fallback to agent")
        return "agent"
