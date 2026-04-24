"""BM25-based retriever for global memory files."""

import os
import re
from typing import List

from rank_bm25 import BM25Okapi


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


class GlobalRetriever:
    """BM25 retriever for cross-session global memory."""

    def __init__(self, global_dir: str = "./memory/global"):
        self.global_dir = global_dir

    def has_trigger(self, text: str) -> bool:
        """Check if text contains any global memory trigger phrase."""
        for pattern in TRIGGER_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """Retrieve top-k most relevant global memory file contents.

        Args:
            query: User input text
            top_k: Maximum number of files to return

        Returns:
            List of file contents, most relevant first
        """
        if not os.path.isdir(self.global_dir):
            return []

        # Load all .md files
        files = sorted(
            f for f in os.listdir(self.global_dir)
            if f.endswith(".md")
        )
        if not files:
            return []

        corpus = []
        file_paths = []
        for fname in files:
            path = os.path.join(self.global_dir, fname)
            try:
                content = self._load_content(path)
                if content:
                    corpus.append(content)
                    file_paths.append(path)
            except OSError:
                continue

        if not corpus:
            return []

        # BM25 scoring
        tokenized_corpus = [doc.lower().split() for doc in corpus]
        bm25 = BM25Okapi(tokenized_corpus)
        query_tokens = query.lower().split()
        scores = bm25.get_scores(query_tokens)

        # Sort by score descending, tie-break by filename (newer first)
        scored = sorted(
            zip(scores, file_paths, corpus),
            key=lambda x: (x[0], x[1]),
            reverse=True,
        )

        return [content for _, _, content in scored[:top_k]]

    def _load_content(self, path: str) -> str:
        """Load file content, skipping front-matter."""
        with open(path, encoding="utf-8") as f:
            content = f.read()

        # Strip front-matter (---...---)
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].lstrip("\n")

        return content.strip()
