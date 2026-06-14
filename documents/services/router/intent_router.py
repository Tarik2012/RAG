import logging

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


def classify_intent(question: str) -> str:
    if not settings.OPENAI_API_KEY:
        logger.warning("Intent router fallback to rag: OPENAI_API_KEY is not set")
        return "rag"

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model="gpt-4o-mini",
            temperature=0,
            instructions=(
                "You are an intent classifier. "
                "Return ONLY one word, with no explanation: rag or agent. "
                "Return agent if the question requires external tools "
                "(web search, GitHub consultation, or multi-step code analysis/navigation). "
                "Return rag if the question can be answered from the user's uploaded documents."
            ),
            input=(question or "").strip(),
        )
        intent = (response.output_text or "").strip().lower()
        if intent in {"rag", "agent"}:
            return intent

        logger.warning("Intent router fallback to rag: invalid model output '%s'", intent)
        return "rag"
    except Exception:
        logger.exception("Intent router fallback to rag")
        return "rag"
