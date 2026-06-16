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
                "You are a message classifier for a document/code assistant. "
                "Return ONLY one word: chat or agent. "
                "Return 'chat' for greetings, thanks, acknowledgements, small talk, "
                "or messages that do not ask anything about documents or code (e.g. 'hola', 'gracias', 'muy bien', 'ok'). "
                "Return 'agent' for any real question or request about the user's files, documents, code, or that needs searching or analysis."
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
