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
