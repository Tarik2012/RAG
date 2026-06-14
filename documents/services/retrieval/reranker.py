from functools import lru_cache

from sentence_transformers import CrossEncoder


@lru_cache(maxsize=2)
def _load_cross_encoder(model_name: str):
    return CrossEncoder(model_name)


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ) -> None:
        self.model = _load_cross_encoder(model_name)

    def rerank(self, query: str, chunks: list[str]) -> list[str]:
        if not chunks:
            return []

        pairs = [[query, chunk] for chunk in chunks]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(chunks, scores), key=lambda item: item[1], reverse=True)
        return [chunk for chunk, _ in ranked]
