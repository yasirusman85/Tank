import json
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
from tank.ai.rag.embeddings import BaseEmbeddings

class BaseVectorStore(ABC):
    def __init__(self, embeddings: BaseEmbeddings):
        self.embeddings = embeddings

    @abstractmethod
    async def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> None:
        """Add list of texts (with optional metadata) into the vector store."""
        pass

    @abstractmethod
    async def similarity_search(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        """Search for top k most similar texts to query, returning dict objects with 'text' and 'metadata'."""
        pass


class SimpleVectorStore(BaseVectorStore):
    """
    A simple, local in-memory vector database.
    Supports persistent dumping/loading to a JSON file.
    Does not require any native binary installations, making it perfect for development.
    """
    def __init__(self, embeddings: BaseEmbeddings, persist_path: Optional[str] = None):
        super().__init__(embeddings)
        self.persist_path = persist_path
        self.documents: List[Dict[str, Any]] = [] # stores {"text": str, "metadata": dict, "vector": List[float]}
        
        if persist_path and os.path.exists(persist_path):
            self.load()

    async def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> None:
        if not texts:
            return
            
        vectors = await self.embeddings.embed_documents(texts)
        for idx, (text, vector) in enumerate(zip(texts, vectors)):
            metadata = metadatas[idx] if metadatas and idx < len(metadatas) else {}
            self.documents.append({
                "text": text,
                "metadata": metadata,
                "vector": vector
            })
            
        if self.persist_path:
            self.save()

    async def similarity_search(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        if not self.documents:
            return []
            
        query_vector = await self.embeddings.embed_query(query)
        
        # Calculate cosine similarity: dot product of normalized vectors
        scores: List[Tuple[float, Dict[str, Any]]] = []
        for doc in self.documents:
            doc_vector = doc["vector"]
            # Cosine similarity formula: dot(A, B) / (norm(A) * norm(B))
            # Since mock/openai embeddings are already normalized (l2 norm = 1.0),
            # cosine similarity is simply the dot product!
            dot_product = sum(q * d for q, d in zip(query_vector, doc_vector))
            scores.append((dot_product, doc))
            
        # Sort by score in descending order
        scores.sort(key=lambda x: x[0], reverse=True)
        
        # Return top k matches as dicts excluding raw vectors
        results = []
        for score, doc in scores[:k]:
            results.append({
                "text": doc["text"],
                "metadata": doc["metadata"],
                "score": score
            })
        return results

    def save(self) -> None:
        """Persist vector store to a JSON file."""
        if not self.persist_path:
            return
        with open(self.persist_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

    def load(self) -> None:
        """Load vector store from a JSON file."""
        if not self.persist_path or not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                self.documents = json.load(f)
        except Exception:
            self.documents = []
