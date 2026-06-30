import logging

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


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
