from django.conf import settings
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

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


def build_rag_tool(retriever, user):
    @tool
    def search_document(query: str) -> str:
        """Search the active user document for information, text, policies, data or any content.
        Use this for general questions about the document content."""
        results = retriever.retrieve(query=query, user=user, top_k=5)
        if not results:
            return "No relevant information found in the document"

        return "\n\n".join(chunk.text for chunk, _ in results)

    return search_document


def build_code_analysis_tool(retriever, user):
    @tool
    def analyze_code(query: str) -> str:
        """Use this tool for ANY request involving code: improving, fixing bugs, optimizing,
        refactoring, explaining, documenting, or reviewing code quality.
        The code is already stored in the active document - retrieve it and analyze it directly.
        Input should be a description of what to analyze, e.g. 'all functions', 'the entire code'."""
        results = retriever.retrieve(query=query, user=user, top_k=10)
        if not results:
            return "No code found in the document"

        return "\n\n".join(chunk.text for chunk, _ in results)

    return analyze_code


def build_agent(user):
    retriever = Retriever(
        embedding_provider=_embedding_provider,
        query_rewriter=_query_rewriter,
        reranker=_reranker,
    )

    tools = [
        build_rag_tool(retriever, user),
        build_code_analysis_tool(retriever, user),
        _tavily_tool,
    ]
    return create_react_agent(_llm, tools, debug=False)
