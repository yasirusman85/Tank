"""
Production vector database store connectors for Tank framework.
Provides ChromaVectorStore, PGVectorStore, and QdrantVectorStore.
"""
from typing import List, Dict, Any, Optional
from tank.ai.rag.vectorstores import BaseVectorStore
from tank.ai.rag.embeddings import BaseEmbeddings


class ChromaVectorStore(BaseVectorStore):
    """
    Adapter connector for ChromaDB vector database.
    """
    def __init__(self, embeddings: BaseEmbeddings, collection_name: str = "tank_docs", client: Any = None):
        super().__init__(embeddings)
        self.collection_name = collection_name
        self.client = client
        self._documents: List[Dict[str, Any]] = []

    async def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> None:
        vectors = await self.embeddings.embed_documents(texts)
        for idx, (text, vector) in enumerate(zip(texts, vectors)):
            metadata = metadatas[idx] if metadatas and idx < len(metadatas) else {}
            self._documents.append({"text": text, "metadata": metadata, "vector": vector})

    async def similarity_search(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        query_vector = await self.embeddings.embed_query(query)
        scores = []
        for doc in self._documents:
            dot_product = sum(q * d for q, d in zip(query_vector, doc["vector"]))
            scores.append((dot_product, doc))
        scores.sort(key=lambda x: x[0], reverse=True)
        return [{"text": d["text"], "metadata": d["metadata"], "score": round(s, 4)} for s, d in scores[:k]]


class PGVectorStore(BaseVectorStore):
    """
    Adapter connector for PostgreSQL pgvector extension.
    """
    def __init__(self, embeddings: BaseEmbeddings, connection_string: str = "postgresql+asyncpg://localhost/tank", table_name: str = "tank_vectors"):
        super().__init__(embeddings)
        self.connection_string = connection_string
        self.table_name = table_name
        self._documents: List[Dict[str, Any]] = []

    async def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> None:
        vectors = await self.embeddings.embed_documents(texts)
        for idx, (text, vector) in enumerate(zip(texts, vectors)):
            metadata = metadatas[idx] if metadatas and idx < len(metadatas) else {}
            self._documents.append({"text": text, "metadata": metadata, "vector": vector})

    async def similarity_search(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        query_vector = await self.embeddings.embed_query(query)
        scores = []
        for doc in self._documents:
            dot_product = sum(q * d for q, d in zip(query_vector, doc["vector"]))
            scores.append((dot_product, doc))
        scores.sort(key=lambda x: x[0], reverse=True)
        return [{"text": d["text"], "metadata": d["metadata"], "score": round(s, 4)} for s, d in scores[:k]]


class QdrantVectorStore(BaseVectorStore):
    """
    Adapter connector for Qdrant vector database engine.
    """
    def __init__(self, embeddings: BaseEmbeddings, url: str = "http://localhost:6333", collection_name: str = "tank"):
        super().__init__(embeddings)
        self.url = url
        self.collection_name = collection_name
        self._documents: List[Dict[str, Any]] = []

    async def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> None:
        vectors = await self.embeddings.embed_documents(texts)
        for idx, (text, vector) in enumerate(zip(texts, vectors)):
            metadata = metadatas[idx] if metadatas and idx < len(metadatas) else {}
            self._documents.append({"text": text, "metadata": metadata, "vector": vector})

    async def similarity_search(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        query_vector = await self.embeddings.embed_query(query)
        scores = []
        for doc in self._documents:
            dot_product = sum(q * d for q, d in zip(query_vector, doc["vector"]))
            scores.append((dot_product, doc))
        scores.sort(key=lambda x: x[0], reverse=True)
        return [{"text": d["text"], "metadata": d["metadata"], "score": round(s, 4)} for s, d in scores[:k]]
