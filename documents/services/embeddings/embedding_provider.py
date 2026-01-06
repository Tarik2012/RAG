from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Recibe una lista de textos y devuelve una lista de embeddings.
        El orden debe mantenerse.
        """
        raise NotImplementedError


class FakeEmbeddingProvider(EmbeddingProvider):
    """
    Provider determinista para tests y desarrollo.
    NO usar en producción.
    """

    DIMENSION = 8

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings: List[List[float]] = []

        for text in texts:
            # embedding determinista y reproducible
            vector = [float((ord(c) % 10)) for c in text[: self.DIMENSION]]
            vector += [0.0] * (self.DIMENSION - len(vector))
            embeddings.append(vector)

        return embeddings
