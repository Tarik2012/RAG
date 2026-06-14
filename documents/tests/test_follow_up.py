import pytest

from documents.views import _build_agent_messages, _looks_like_follow_up


def test_looks_like_follow_up_with_reference():
    assert _looks_like_follow_up("y cuantas funciones tiene ese archivo")
    assert _looks_like_follow_up("eso que hace")
    assert _looks_like_follow_up("lo anterior era correcto?")


def test_looks_like_follow_up_with_prefix():
    assert _looks_like_follow_up("y que mas hace?")
    assert _looks_like_follow_up("entonces como funciona?")
    assert _looks_like_follow_up("tambien tiene tests?")


def test_not_follow_up_for_new_question():
    assert not _looks_like_follow_up("que hace document_processor.py")
    assert not _looks_like_follow_up("cuantos archivos tiene el repo")
    assert not _looks_like_follow_up("explica el pipeline de ingesta")


@pytest.mark.django_db
def test_build_agent_messages_no_history_for_new_question(django_user_model):
    user = django_user_model.objects.create_user(
        username="follow-up-new-question",
        password="pass1234",
    )
    history = [
        {"role": "user", "content": "explica document_processor.py"},
        {"role": "assistant", "content": "procesa documentos y chunks"},
    ]

    messages = _build_agent_messages(
        user=user,
        question="que hace document_processor.py",
        history=history,
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "que hace document_processor.py"}


@pytest.mark.django_db
def test_build_agent_messages_includes_history_for_follow_up(django_user_model):
    user = django_user_model.objects.create_user(
        username="follow-up-history",
        password="pass1234",
    )
    history = [
        {"role": "user", "content": "explica document_processor.py"},
        {"role": "assistant", "content": "procesa documentos y chunks"},
    ]

    messages = _build_agent_messages(
        user=user,
        question="y ese archivo?",
        history=history,
    )

    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[1:] == [
        {"role": "user", "content": "explica document_processor.py"},
        {"role": "assistant", "content": "procesa documentos y chunks"},
        {"role": "user", "content": "y ese archivo?"},
    ]
