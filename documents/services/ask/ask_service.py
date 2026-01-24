from typing import Dict, List

from documents.services.retrieval.retriever import Retriever
from documents.services.llm.llm_provider import LLMProvider


class AskService:
    """
    AskService seguro y determinista:
    - No llama al LLM sin contexto
    - Cero alucinaciones
    """

    def __init__(self, *, retriever: Retriever, llm_provider: LLMProvider):
        self.retriever = retriever
        self.llm_provider = llm_provider

    def ask(
        self,
        *,
        question: str,
        user,
        top_k: int = 5,
    ) -> Dict:
        results = self.retriever.retrieve(
            query=question,
            user=user,
            top_k=top_k,
        )

        if not results:
            return {
                "question": question,
                "answer": (
                    "No tengo información suficiente en el documento activo "
                    "para responder a esta pregunta."
                ),
                "context": "",
                "chunks_used": 0,
            }

        context_chunks: List[str] = [chunk.text for chunk, _ in results]
        context = "\n\n".join(context_chunks)

        answer = self.llm_provider.generate(
            question=question,
            context=context,
        )

        return {
            "question": question,
            "answer": answer,
            "context": context,
            "chunks_used": len(context_chunks),
        }
