from documents.services.llm.llm_provider import LLMProvider


class FakeLLMProvider(LLMProvider):
    def generate(self, *, question: str, context: str) -> str:
        return (
            "FAKE ANSWER\n"
            f"QUESTION: {question}\n"
            f"CONTEXT: {context[:200]}"
        )
