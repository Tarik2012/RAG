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

    def embed_texts(self, texts: List[str], batch_size: int = 256) -> List[List[float]]:
        if not texts:
            return []

        embeddings: List[List[float]] = []

        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            response = self.client.embeddings.create(
                model=self.model_name,
                input=batch,
            )
            embeddings.extend(item.embedding for item in response.data)

        return embeddings
