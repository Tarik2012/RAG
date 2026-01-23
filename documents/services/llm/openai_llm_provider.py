from openai import OpenAI
from django.conf import settings

from .llm_provider import LLMProvider


class OpenAILLMProvider(LLMProvider):
    """
    Real LLM provider using OpenAI Responses API.
    """

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate(self, *, question: str, context: str) -> str:
        instructions = (
            "You are a RAG assistant. "
            "Answer using ONLY the provided context. "
            "You may paraphrase or combine ideas from the context, "
            "but you must not use external knowledge. "
            "If the answer cannot be found or reasonably inferred from the context, "
            "respond politely explaining that the information is not available "
            "in the uploaded documents and suggest asking a more specific or related question. "
            "Keep a friendly, helpful tone."
        )

        prompt = (
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION:\n{question}\n"
        )

        response = self.client.responses.create(
            model=settings.OPENAI_MODEL,
            instructions=instructions,
            input=prompt,
        )

        return response.output_text
