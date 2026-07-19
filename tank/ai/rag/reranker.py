"""
Reranking primitives for Tank RAG pipelines.
Re-scores and re-orders document search candidates to improve retrieval relevance.
"""
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseReranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 4
    ) -> List[Dict[str, Any]]:
        """Rerank list of candidate document dicts based on relevance to query."""
        pass


class SimpleReranker(BaseReranker):
    """
    Zero-dependency keyword overlap & term frequency reranker.
    Boosts candidate scores based on query term matches and exact phrase occurrences.
    """
    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 4
    ) -> List[Dict[str, Any]]:
        if not documents:
            return []

        query_terms = set(re.findall(r'\w+', query.lower()))
        query_phrase = query.strip().lower()

        scored_docs = []
        for doc in documents:
            text = str(doc.get("text", "")).lower()
            initial_score = float(doc.get("score", 0.0))

            # Overlap score
            text_terms = set(re.findall(r'\w+', text))
            overlap = len(query_terms.intersection(text_terms)) if query_terms else 0
            overlap_bonus = (overlap / len(query_terms)) * 0.5 if query_terms else 0.0

            # Exact phrase match bonus
            phrase_bonus = 0.3 if query_phrase and query_phrase in text else 0.0

            final_score = initial_score + overlap_bonus + phrase_bonus
            doc_copy = dict(doc)
            doc_copy["score"] = round(final_score, 4)
            scored_docs.append(doc_copy)

        scored_docs.sort(key=lambda d: d["score"], reverse=True)
        return scored_docs[:top_k]
