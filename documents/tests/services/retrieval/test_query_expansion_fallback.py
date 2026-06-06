from documents.services.retrieval.retriever import _expand_or_fallback


class _BoomRewriter:
    def expand(self, query):
        raise RuntimeError("provider down")


class _OkRewriter:
    def expand(self, query):
        return [query, query + " variante"]


def test_fallback_to_original_on_error():
    assert _expand_or_fallback(_BoomRewriter(), "hola") == ["hola"]


def test_uses_rewriter_result_when_ok():
    assert _expand_or_fallback(_OkRewriter(), "hola") == ["hola", "hola variante"]


def test_no_rewriter_returns_original():
    assert _expand_or_fallback(None, "hola") == ["hola"]
