from django.conf import settings
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from documents.models import Document
from documents.services.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker
from documents.services.retrieval.retriever import Retriever

_reranker = CrossEncoderReranker()
_embedding_provider = OpenAIEmbeddingProvider()
_query_rewriter = QueryRewriter()
_llm = ChatOpenAI(
    model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
    temperature=0,
)
_tavily_tool = TavilySearchResults(max_results=3)


def _get_active_document(user):
    return Document.objects.filter(
        owner=user,
        is_active=True,
        status="processed",
    ).first()


def _get_document_full_text(document) -> str:
    stored_file = getattr(document, "file", None)
    if stored_file:
        stored_file.open("rb")
        try:
            stored_file.seek(0)
            file_text = stored_file.read().decode("utf-8", errors="ignore")
        finally:
            stored_file.close()

        if file_text.strip():
            return file_text

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
    return create_react_agent(_llm, tools, debug=False)
