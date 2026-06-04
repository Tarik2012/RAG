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

    def expand(self, question: str, n: int = 3) -> list[str]:
        cleaned = (question or "").strip()
        if not cleaned:
            return [question]

        instructions = (
            "You are a query expansion assistant for document retrieval. "
            f"Generate {n} alternative phrasings of the user's question that keep "
            "the same intent but use different wording and synonyms. "
            "Use only information present in the question; do NOT answer it or add external knowledge. "
            "Return each alternative on its own line, with no numbering, bullets, or extra text."
        )

        response = self.client.responses.create(
            model=settings.OPENAI_MODEL,
            instructions=instructions,
            input=cleaned,
        )

        text = response.output_text or ""
        variants = [line.strip() for line in text.splitlines() if line.strip()]

        # Siempre incluir la original; deduplicar preservando el orden
        seen = set()
        unique: list[str] = []
        for q in [cleaned] + variants:
            key = q.lower()
            if key not in seen:
                seen.add(key)
                unique.append(q)
        return unique
