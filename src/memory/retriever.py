"""BM25-based retriever for global memory files."""

import os
import re
from typing import List, Optional

import jieba
from rank_bm25 import BM25Plus

# Pre-load jieba dictionary at module level for faster first use
jieba.initialize()


# Trigger patterns for global memory recall
TRIGGER_PATTERNS = [
    r"还记得",
    r"记得",
    r"上次",
    r"之前",
    r"以前",
    r"继续",
    r"之前.*说过",
    r"之前.*提到",
    r"还记得.*吗",
    r"以前.*提到",
    r"那(?:次|个|次|天)",
    r"继续.*上",
    r"上.*(?:次|回|会话)",
]


def tokenize_cn(text: str) -> List[str]:
    """Chinese word segmentation using jieba + English word split.

    Chinese: jieba cutting for proper word boundaries.
    English/Python: word-level matching on whitespace.
    """
    words = []
    for word in jieba.cut(text.lower()):
        if word.strip():
            words.append(word)
    return words


class GlobalRetriever:
    """BM25 retriever for cross-session global memory."""

    def __init__(self, global_dir: str = "./memory/global"):
        self.global_dir = global_dir
        self.global_file = os.path.join(global_dir, "memory.md")
        self._index: Optional[BM25Plus] = None
        self._content_cache: List[str] = []

    def _build_index(self) -> None:
        """Build BM25 index from single memory.md file.

        Parses entries by "---" separator, extracts body (skips front-matter).
        Handles malformed entries by skipping them (with warning logged).
        """
        self._content_cache = []

        if not os.path.exists(self.global_file):
            self._index = None
            return

        with open(self.global_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by \n---\n separator to get entries
        entries = content.split("\n---\n")

        for entry in entries:
            if not entry.strip():
                continue

            # Try to extract body (skip front-matter)
            if entry.startswith("---"):
                # Has front-matter: split twice to get body
                parts = entry.split("\n---\n", 1)
                if len(parts) > 1:
                    body = parts[1]
                else:
                    body = entry
            else:
                # No front-matter, use entire entry
                body = entry

            body = body.strip()
            if body:
                self._content_cache.append(body)

        # Build BM25 index
        if self._content_cache:
            tokenized_corpus = [tokenize_cn(doc) for doc in self._content_cache]
            self._index = BM25Plus(tokenized_corpus)
        else:
            self._index = None

    def has_trigger(self, text: str) -> bool:
        """Check if text contains any global memory trigger phrase."""
        for pattern in TRIGGER_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """Retrieve top-k most relevant global memory entries.

        Only returns entries with a non-zero BM25 score.
        Re-builds index if not yet built (lazy init).

        Args:
            query: User input text
            top_k: Maximum number of entries to return

        Returns:
            List of entry contents, most relevant first
        """
        if self._index is None:
            self._build_index()

        if not self._content_cache or self._index is None:
            return []

        query_tokens = tokenize_cn(query)
        scores = self._index.get_scores(query_tokens)

        # Pair scores with content
        scored = sorted(
            enumerate(zip(self._content_cache, scores)),
            key=lambda x: x[1][1],
            reverse=True,
        )

        # Filter zero scores, take top_k
        result = [content for idx, (content, score) in scored if score > 0][:top_k]
        return result