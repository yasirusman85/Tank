import os
import hashlib
from abc import ABC, abstractmethod
from typing import List

class BaseEmbeddings(ABC):
    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query string."""
        pass

    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of document strings."""
        pass


class MockEmbeddings(BaseEmbeddings):
    """
    A zero-dependency mock embeddings model.
    Maps words to unique indices in a dynamic vocabulary to simulate
    true semantic keyword overlap without collisions.
    """
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.vocab = {}
        self.vocab_counter = 0

    def _generate_vector(self, text: str) -> List[float]:
        import re
        words = re.findall(r'\w+', text.lower())
        vector = [0.0] * self.dimension
        if not words:
            vector[0] = 1.0
            return vector
            
        for word in words:
            if word not in self.vocab:
                self.vocab[word] = self.vocab_counter % self.dimension
                self.vocab_counter += 1
            idx = self.vocab[word]
            vector[idx] += 1.0
            
        # Normalize vector (l2 norm) to make cosine similarity clean
        magnitude = sum(x*x for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        else:
            vector[0] = 1.0
            
        return vector

    async def embed_query(self, text: str) -> List[float]:
        return self._generate_vector(text)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_vector(t) for t in texts]



class OpenAIEmbeddings(BaseEmbeddings):
    """
    Integrates with the official OpenAI embeddings client.
    """
    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    async def embed_query(self, text: str) -> List[float]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.embeddings.create(
            input=[text],
            model=self.model
        )
        return response.data[0].embedding

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.embeddings.create(
            input=texts,
            model=self.model
        )
        # Sort by index to maintain correct order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]
