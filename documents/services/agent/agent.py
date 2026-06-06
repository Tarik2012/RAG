import logging
import os
from functools import lru_cache
from typing import TypedDict

from asgiref.sync import async_to_sync
from django.conf import settings
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent

from documents.models import Document
from documents.services.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker
from documents.services.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)
_reranker = CrossEncoderReranker()
_embedding_provider = OpenAIEmbeddingProvider()
_query_rewriter = QueryRewriter()
_llm = ChatOpenAI(
    model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
    temperature=0,
)
_tavily_tool = TavilySearchResults(max_results=3)
_MCP_CONFIG = {
    "github": {
        "url": "https://api.githubcopilot.com/mcp/",
        "transport": "streamable_http",
        "headers": {"Authorization": f"Bearer {os.environ.get('GITHUB_PAT', '')}"},
    }
}
_MCP_TOOL_ALLOWLIST = {"get_file_contents", "search_code"}
MAX_RETRIES = 1


@lru_cache(maxsize=1)
def _get_mcp_tools():
    try:
        client = MultiServerMCPClient(_MCP_CONFIG)
        tools = list(async_to_sync(client.get_tools)())
        return [t for t in tools if t.name in _MCP_TOOL_ALLOWLIST]
    except Exception as exc:
        logger.warning("No se pudieron cargar las tools MCP: %s", exc)
        return []


def _get_active_document(user):
    return Document.objects.filter(
        owner=user,
        is_active=True,
        status="processed",
    ).first()


def _get_document_full_text(document) -> str:
    stored_file = getattr(document, "file", None)
    if stored_file:
        try:
            stored_file.open("rb")
            try:
                stored_file.seek(0)
                file_text = stored_file.read().decode("utf-8", errors="ignore")
            finally:
                stored_file.close()
            if file_text.strip():
                return file_text
        except (FileNotFoundError, OSError):
            pass  # archivo no disponible -> usar fallback de chunks

    # Last resort only: reconstruct from chunks if the original file is unavailable.
    chunks = document.chunks.order_by("order").values_list("text", flat=True)
    return "\n\n".join(chunk for chunk in chunks if chunk)


def build_rag_tool(retriever, user):
    @tool
    def search_document(query: str) -> str:
        """Search the active user document for information, text, policies, data or any content.
        Use this for general questions about the document content."""
        print(">>> TOOL USED: search_document", flush=True)
        results = retriever.retrieve(query=query, user=user, top_k=5)
        if not results:
            return "No relevant information found in the document"

        return "\n\n".join(chunk.text for chunk, _ in results)

    return search_document


def build_code_analysis_tool(retriever, user):
    @tool
    def analyze_code(query: str) -> str:
        """Use this tool for ANY request involving code: improving, fixing bugs, optimizing,
        refactoring, explaining, documenting, reviewing code quality, or auditing security.
        Always inspect the full active code file, always check for hardcoded secrets or credentials,
        and report only issues that are actually present in the code you received.
        Do not invent duplicates, vulnerabilities, or missing pieces that are not visible in the file.
        Input should describe what to analyze, e.g. 'all functions', 'the entire code', or 'security review'."""
        print(">>> TOOL USED: analyze_code", flush=True)
        active_document = _get_active_document(user)
        if active_document is None:
            return "No code found in the document"

        full_text = _get_document_full_text(active_document)
        if not full_text.strip():
            return "No code found in the document"

        return (
            "Analysis instructions:\n"
            f"- User request: {query}\n"
            "- Review the full code below.\n"
            "- Always check for hardcoded secrets, credentials, tokens, or API keys.\n"
            "- Report only issues that are truly present in this code.\n"
            "- Do not claim duplicated logic, bugs, or vulnerabilities unless the code below shows them.\n\n"
            "Full file content:\n"
            f"{full_text}"
        )

    return analyze_code


def build_tavily_tool():
    @tool("tavily_search")
    def tavily_search(query: str) -> str:
        """Search the web for recent external information when the active document is insufficient."""
        print(">>> TOOL USED: tavily_search", flush=True)
        result = _tavily_tool.invoke({"query": query})
        return str(result)

    return tavily_search


class AgentState(TypedDict, total=False):
    messages: list
    answer_ok: bool
    retries: int


def build_agent(user):
    retriever = Retriever(
        embedding_provider=_embedding_provider,
        query_rewriter=_query_rewriter,
        reranker=_reranker,
    )

    tools = [
        build_rag_tool(retriever, user),
        build_code_analysis_tool(retriever, user),
        build_tavily_tool(),
    ]
    tools = tools + _get_mcp_tools()

    react_agent = create_react_agent(_llm, tools, debug=False)

    def run_agent(state: AgentState) -> dict:
        result = async_to_sync(react_agent.ainvoke)({"messages": state["messages"]})
        return {"messages": result["messages"]}

    def reflect(state: AgentState) -> dict:
        messages = state["messages"]
        question = next(
            (m.content for m in messages if getattr(m, "type", None) == "human"),
            "",
        )
        answer = messages[-1].content if messages else ""

        grader_prompt = (
            "You are a strict grader for a question-answering assistant. "
            "Given the user's QUESTION and the assistant's ANSWER, decide if the answer "
            "actually addresses the question with concrete, relevant content. "
            "If the answer fails to find the information, is empty, evasive, or off-topic, output RETRY. "
            "Otherwise output GOOD. Respond with exactly one word: GOOD or RETRY.\n\n"
            f"QUESTION:\n{question}\n\nANSWER:\n{answer}"
        )
        verdict = (_llm.invoke(grader_prompt).content or "").strip().upper()
        answer_ok = "RETRY" not in verdict
        print(f">>> REFLECT verdict={verdict} answer_ok={answer_ok}", flush=True)
        return {"answer_ok": answer_ok}

    def reformulate(state: AgentState) -> dict:
        messages = list(state["messages"])
        original_question = next(
            (m.content for m in messages if getattr(m, "type", None) == "human"),
            "",
        )
        reformulated_question = _query_rewriter.reformulate(original_question)
        messages.append(HumanMessage(content=reformulated_question))
        retries = state.get("retries", 0) + 1
        print(f">>> REFORMULATE retries={retries}", flush=True)
        return {"messages": messages, "retries": retries}

    def should_retry(state: AgentState) -> str:
        if state["answer_ok"] is True:
            return "end"
        if state.get("retries", 0) >= MAX_RETRIES:
            return "end"
        return "retry"

    builder = StateGraph(AgentState)
    builder.add_node("run_agent", run_agent)
    builder.add_node("reflect", reflect)
    builder.add_node("reformulate", reformulate)
    builder.add_edge(START, "run_agent")
    builder.add_edge("run_agent", "reflect")
    builder.add_conditional_edges(
        "reflect",
        should_retry,
        {
            "retry": "reformulate",
            "end": END,
        },
    )
    builder.add_edge("reformulate", "run_agent")
    return builder.compile()
