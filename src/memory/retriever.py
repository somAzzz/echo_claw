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


def tokenize_cn(text: str) -> List[str]:
    """Character bigram tokenization for Chinese + English word split.

    Chinese: character bigrams for sub-character matching.
    English/Python: word-level matching on whitespace.
    """
    chars = list(text.lower())
    bigrams = [''.join(chars[i:i+2]) for i in range(len(chars)-1)]
    words = text.lower().split()
    return bigrams + words


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

        Only returns files with a non-zero BM25 score.
        Tie-breaking by filename descending = newer session first.

        Args:
            query: User input text
            top_k: Maximum number of files to return

        Returns:
            List of file contents, most relevant first
        """
        if not os.path.isdir(self.global_dir):
            return []

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

        tokenized_corpus = [tokenize_cn(doc) for doc in corpus]
        bm25 = BM25Okapi(tokenized_corpus)
        query_tokens = tokenize_cn(query)
        scores = bm25.get_scores(query_tokens)

        # Sort: descending score (primary), descending filename (tie-break = newest first)
        # reverse=True: (high_score → low_score), (z → a) for filenames
        scored = sorted(
            zip(scores, file_paths, corpus),
            key=lambda x: (x[0], x[1]),
            reverse=True,
        )

        # Filter zero scores, take top_k
        result = [content for score, _, content in scored if score > 0][:top_k]
        return result

    def _load_content(self, path: str) -> str:
        """Load file content, skipping front-matter."""
        with open(path, encoding="utf-8") as f:
            content = f.read()

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].lstrip("\n")

        return content.strip()
