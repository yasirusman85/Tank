from tank.ai.rag.vectorstores import BaseVectorStore
from tank.ai.tools import Tool

class Retriever:
    """
    Wraps a VectorStore to generate a dynamic search tool that can be used directly
    by Tank agents to retrieve matching context from knowledge bases.
    """
    def __init__(self, vector_store: BaseVectorStore, k: int = 3):
        self.vector_store = vector_store
        self.k = k

    def as_tool(
        self,
        name: str = "retrieve_context",
        description: str = "Search documentation and retrieve relevant context based on query keyword search."
    ) -> Tool:
        """
        Builds a standard Tank tool wrapper around similarity searches.
        """
        async def retrieve(query: str) -> str:
            results = await self.vector_store.similarity_search(query, k=self.k)
            if not results:
                return "No matching documents found in the database."
                
            formatted = []
            for idx, doc in enumerate(results):
                formatted.append(f"[Match {idx + 1} (Score: {doc['score']:.4f})]:\n{doc['text']}")
                
            return "\n\n".join(formatted)

        # Apply name and docstring dynamically for schema compilation
        retrieve.__name__ = name
        retrieve.__doc__ = description

        return Tool(retrieve)
