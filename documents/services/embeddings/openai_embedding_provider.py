from typing import List

from django.conf import settings
from openai import OpenAI

from .embedding_provider import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, *, model_name: str = "text-embedding-3-small") -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")

        self.model_name = model_name
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts,
        )

        return [item.embedding for item in response.data]
