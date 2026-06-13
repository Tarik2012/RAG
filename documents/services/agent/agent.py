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
from documents.services.extraction.text_extraction import get_document_full_text
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker
from documents.services.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_reranker():
    return CrossEncoderReranker()


@lru_cache(maxsize=1)
def _get_embedding_provider():
    return OpenAIEmbeddingProvider()


@lru_cache(maxsize=1)
def _get_query_rewriter():
    return QueryRewriter()


@lru_cache(maxsize=1)
def _get_llm():
    return ChatOpenAI(
        model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
    )


@lru_cache(maxsize=1)
def _get_tavily_tool():
    return TavilySearchResults(max_results=3)


def _build_mcp_config():
    return {
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
        client = MultiServerMCPClient(_build_mcp_config())
        tools = list(async_to_sync(client.get_tools)())
        return [t for t in tools if t.name in _MCP_TOOL_ALLOWLIST]
    except Exception as exc:
        logger.warning("No se pudieron cargar las tools MCP: %s", exc)
        return []


def build_rag_tool(retriever, user):
    @tool
    def search_document(query: str) -> str:
        """Search the user's documents for information, text, policies, data or any content.
        Use this for general questions about the document content."""
        logger.info("tool used: search_document")
        results = retriever.retrieve(query=query, user=user, top_k=5)
        if not results:
            return "No relevant information found in the document"

        return "\n\n".join(chunk.text for chunk, _ in results)

    return search_document


def build_code_analysis_tool(retriever, user):
    @tool
    def analyze_code(query: str, document_name: str) -> str:
        """Use this tool for ANY request involving code: improving, fixing bugs, optimizing,
        refactoring, explaining, documenting, reviewing code quality, or auditing security.
        'document_name' is the name of the file to analyze (one of the user's uploaded files).
        Review the full code, always check for hardcoded secrets/credentials, and report only
        issues actually present in the code. Do not invent problems not visible in the file."""
        logger.info("tool used: analyze_code")
        document = Document.objects.filter(
            owner=user, status="processed", original_name__icontains=document_name,
        ).first()
        if document is None:
            available = list(
                Document.objects.filter(owner=user, status="processed")
                .values_list("original_name", flat=True)
            )
            return f"No file matching '{document_name}'. Available files: {', '.join(available) or 'none'}."
        full_text = get_document_full_text(document)
        if not full_text.strip():
            return "No code found in the document"
        MAX_CHARS = 80000
        truncated = full_text[:MAX_CHARS]
        nota = "" if len(full_text) <= MAX_CHARS else "\n\n[Note: file truncated due to size.]"
        return (
            "Analysis instructions:\n"
            f"- User request: {query}\n"
            f"- File analyzed: {document.original_name}\n"
            "- Review the full code below.\n"
            "- Always check for hardcoded secrets, credentials, tokens, or API keys.\n"
            "- Report only issues that are truly present in this code.\n\n"
            "Full file content:\n"
            f"{truncated}{nota}"
        )

    return analyze_code


def build_tavily_tool():
    @tool("tavily_search")
    def tavily_search(query: str) -> str:
        """Search the web for recent external information when the active document is insufficient."""
        logger.info("tool used: tavily_search")
        result = _get_tavily_tool().invoke({"query": query})
        return str(result)

    return tavily_search


class AgentState(TypedDict, total=False):
    messages: list
    answer_ok: bool
    retries: int


def build_agent(user):
    retriever = Retriever(
        embedding_provider=_get_embedding_provider(),
        query_rewriter=_get_query_rewriter(),
        reranker=_get_reranker(),
    )

    tools = [
        build_rag_tool(retriever, user),
        build_code_analysis_tool(retriever, user),
        build_tavily_tool(),
    ]
    tools = tools + _get_mcp_tools()

    llm = _get_llm()
    query_rewriter = _get_query_rewriter()
    react_agent = create_react_agent(llm, tools, debug=False)

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
        verdict = (llm.invoke(grader_prompt).content or "").strip().upper()
        answer_ok = verdict.startswith("GOOD")
        logger.debug("reflect verdict=%s answer_ok=%s", verdict, answer_ok)
        return {"answer_ok": answer_ok}

    def reformulate(state: AgentState) -> dict:
        messages = list(state["messages"])
        original_question = next(
            (m.content for m in messages if getattr(m, "type", None) == "human"),
            "",
        )
        reformulated_question = query_rewriter.reformulate(original_question)
        messages.append(HumanMessage(content=reformulated_question))
        retries = state.get("retries", 0) + 1
        logger.debug("reformulate retries=%s", retries)
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
