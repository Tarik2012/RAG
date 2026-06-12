import pytest
from langchain_core.messages import AIMessage, HumanMessage
from types import SimpleNamespace

from documents.models import Document, DocumentChunk
from documents.services.agent import agent
from documents.services.extraction.text_extraction import get_document_full_text


pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="agent-tester",
        password="pass1234",
    )


def test_get_document_full_text_concatenates_all_chunks_in_order(user):
    document = Document.objects.create(
        owner=user,
        original_name="sample.py",
        file="documents/sample.py",
        content_type="text/plain",
        size=42,
        status="processed",
    )

    DocumentChunk.objects.create(document=document, order=2, text="third()")
    DocumentChunk.objects.create(document=document, order=0, text="first()")
    DocumentChunk.objects.create(document=document, order=1, text="second()")

    assert get_document_full_text(document) == "first()\n\nsecond()\n\nthird()"


def test_get_document_full_text_prefers_original_file_content(user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    file_path = tmp_path / "documents"
    file_path.mkdir()
    original_file = file_path / "sample.py"
    original_file.write_text("print('from file')\nprint('exact source')", encoding="utf-8")

    document = Document.objects.create(
        owner=user,
        original_name="sample.py",
        file="documents/sample.py",
        content_type="text/plain",
        size=original_file.stat().st_size,
        status="processed",
    )

    DocumentChunk.objects.create(document=document, order=0, text="print('chunk overlap')")
    DocumentChunk.objects.create(document=document, order=1, text="print('chunk overlap')")

    assert get_document_full_text(document) == "print('from file')\nprint('exact source')"


def test_build_agent_retries_once_then_succeeds(monkeypatch, user):
    reformulations = []
    run_calls = []
    grade_calls = []

    class FakeReactAgent:
        def invoke(self, payload):
            run_calls.append([message.content for message in payload["messages"]])
            answer = "first answer" if len(run_calls) == 1 else "second answer"
            return {
                "messages": [
                    *payload["messages"],
                    AIMessage(content=answer),
                ]
            }

        async def ainvoke(self, *args, **kwargs):
            return self.invoke(*args, **kwargs)

    class FakeLLM:
        def invoke(self, prompt):
            grade_calls.append(prompt)
            verdict = "RETRY" if len(grade_calls) == 1 else "GOOD"
            return SimpleNamespace(content=verdict)

    def fake_reformulate(question):
        reformulations.append(question)
        return f"Reformulated: {question}"

    monkeypatch.setattr(agent, "create_react_agent", lambda *args, **kwargs: FakeReactAgent())
    monkeypatch.setattr(agent, "_llm", FakeLLM())
    monkeypatch.setattr(agent._query_rewriter, "reformulate", fake_reformulate)

    graph = agent.build_agent(user)
    result = graph.invoke({"messages": [HumanMessage(content="Where is the policy?")]})

    assert result["answer_ok"] is True
    assert result["retries"] == 1
    assert reformulations == ["Where is the policy?"]
    assert len(run_calls) == 2
    assert run_calls[1][-1] == "Reformulated: Where is the policy?"


def test_build_agent_stops_after_max_retries(monkeypatch, user):
    reformulations = []
    run_calls = []
    grade_calls = []

    class FakeReactAgent:
        def invoke(self, payload):
            run_calls.append([message.content for message in payload["messages"]])
            return {
                "messages": [
                    *payload["messages"],
                    AIMessage(content=f"answer {len(run_calls)}"),
                ]
            }

        async def ainvoke(self, *args, **kwargs):
            return self.invoke(*args, **kwargs)

    class FakeLLM:
        def invoke(self, prompt):
            grade_calls.append(prompt)
            return SimpleNamespace(content="RETRY")

    def fake_reformulate(question):
        reformulations.append(question)
        return f"Reformulated: {question}"

    monkeypatch.setattr(agent, "create_react_agent", lambda *args, **kwargs: FakeReactAgent())
    monkeypatch.setattr(agent, "_llm", FakeLLM())
    monkeypatch.setattr(agent._query_rewriter, "reformulate", fake_reformulate)

    graph = agent.build_agent(user)
    result = graph.invoke({"messages": [HumanMessage(content="Explain the bug")]})

    assert result["answer_ok"] is False
    assert result["retries"] == agent.MAX_RETRIES
    assert reformulations == ["Explain the bug"]
    assert len(run_calls) == agent.MAX_RETRIES + 1
    assert len(grade_calls) == agent.MAX_RETRIES + 1
