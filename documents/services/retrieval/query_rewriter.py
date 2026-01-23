from django.conf import settings
from openai import OpenAI


class QueryRewriter:
    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def rewrite(self, question: str) -> str:
        cleaned = (question or "").strip()
        if not cleaned:
            return question
        instructions = (
            "You are a query rewriting assistant for document retrieval. "
            "Rewrite the user's question to be more explicit and specific. "
            "Clarify vague terms using only information already present in the question. "
            "Do NOT answer the question and do NOT introduce external knowledge. "
            "If no rewrite is needed, return the original question. "
            "Return only the rewritten question and nothing else."
        )

        response = self.client.responses.create(
            model=settings.OPENAI_MODEL,
            instructions=instructions,
            input=cleaned,
        )

        rewritten = response.output_text
        if not rewritten or not rewritten.strip():
            return cleaned

        return rewritten.strip()
