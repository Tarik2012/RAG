from langchain_core.tools import Tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from documents.services.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker
from documents.services.retrieval.retriever import Retriever


def build_rag_tool(user):
    retriever = Retriever(
        embedding_provider=OpenAIEmbeddingProvider(),
        query_rewriter=QueryRewriter(),
        reranker=CrossEncoderReranker(),
    )

    def search_document(query: str) -> str:
        results = retriever.retrieve(query=query, user=user, top_k=5)
        if not results:
            return "No relevant information found in the document"

        return "\n\n".join(chunk.text for chunk, _ in results)

    return Tool(
        name="DocumentSearch",
        func=search_document,
        description="Search the active user document for relevant information.",
    )


def build_agent(user):
    rag_tool = build_rag_tool(user)
    tavily_tool = TavilySearchResults(max_results=3)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [rag_tool, tavily_tool]
    return create_react_agent(llm, tools, debug=True)
