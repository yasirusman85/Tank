"""
Text chunking utilities for Tank RAG pipelines.
Provides RecursiveTextSplitter to break long documents into overlapping chunks.
"""
from typing import List


class RecursiveTextSplitter:
    """
    Splits text recursively by separators (\n\n, \n, . , ' ', '') to preserve
    semantic structure while enforcing chunk_size and chunk_overlap constraints.
    """
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: List[str] | None = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []
        return self._split(text, self.separators)

    def _split(self, text: str, separators: List[str]) -> List[str]:
        if len(text) <= self.chunk_size or not separators:
            return [text] if text.strip() else []

        sep = separators[0]
        splits = text.split(sep) if sep else list(text)
        next_separators = separators[1:]

        chunks = []
        current_chunk = []
        current_length = 0

        for split in splits:
            item = split + (sep if sep else "")
            item_len = len(item)

            if item_len > self.chunk_size and next_separators:
                # Sub-split large chunk with finer separator
                sub_chunks = self._split(split, next_separators)
                for sc in sub_chunks:
                    chunks.append(sc.strip())
                continue

            if current_length + item_len > self.chunk_size:
                if current_chunk:
                    chunk_text = "".join(current_chunk).strip()
                    if chunk_text:
                        chunks.append(chunk_text)
                    # Handle overlap
                    overlap_len = 0
                    overlap_items = []
                    for prev_item in reversed(current_chunk):
                        if overlap_len + len(prev_item) <= self.chunk_overlap:
                            overlap_items.insert(0, prev_item)
                            overlap_len += len(prev_item)
                        else:
                            break
                    current_chunk = overlap_items
                    current_length = sum(len(x) for x in current_chunk)

            current_chunk.append(item)
            current_length += item_len

        if current_chunk:
            final_text = "".join(current_chunk).strip()
            if final_text and (not chunks or chunks[-1] != final_text):
                chunks.append(final_text)

        return [c for c in chunks if c.strip()]
