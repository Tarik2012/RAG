from documents.services.retrieval.reranker import _load_cross_encoder


def test_cross_encoder_model_cached():
    a = _load_cross_encoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    b = _load_cross_encoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    assert a is b
