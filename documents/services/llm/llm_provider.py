from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, *, question: str, context: str) -> str:
        """
        Genera una respuesta usando la pregunta y el contexto.
        """
        raise NotImplementedError
