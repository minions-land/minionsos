"""BM25 query functionality extracted from book.py.

This module provides BM25-based retrieval over Book pages.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

# BM25 parameters
K1 = 1.5
B = 0.75

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_COMMON_SHARED_TERMS = frozenset({
    "about", "across", "after", "again", "among", "around", "because",
    "before", "behind", "being", "below", "between", "beyond", "could",
    "during", "first", "frontmatter", "index", "instead", "other", "page",
    "pages", "shared", "should", "since"
})


def tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize text for BM25 scoring."""
    text_lower = text.lower()
    tokens = _TOKEN_RE.findall(text_lower)
    return [t for t in tokens if len(t) > 2 and t not in _COMMON_SHARED_TERMS]


def compute_bm25_scores(
    query_tokens: list[str],
    documents: list[dict[str, Any]],
) -> dict[int, float]:
    """Compute BM25 scores for documents given query tokens.

    Args:
        query_tokens: List of query tokens
        documents: List of dicts with 'text' field

    Returns:
        Dict mapping document index to BM25 score
    """
    if not documents:
        return {}

    # Tokenize all documents
    doc_tokens = [tokenize_for_bm25(doc.get('text', '')) for doc in documents]

    # Compute document frequencies
    df: dict[str, int] = defaultdict(int)
    for tokens in doc_tokens:
        for token in set(tokens):
            df[token] += 1

    # Compute average document length
    doc_lengths = [len(tokens) for tokens in doc_tokens]
    avg_doc_len = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 1.0

    # Compute BM25 scores
    num_docs = len(documents)
    scores: dict[int, float] = {}

    for idx, tokens in enumerate(doc_tokens):
        score = 0.0
        term_freqs: dict[str, int] = defaultdict(int)

        for token in tokens:
            term_freqs[token] += 1

        doc_len = doc_lengths[idx]

        for query_token in query_tokens:
            if query_token not in term_freqs:
                continue

            tf = term_freqs[query_token]
            doc_freq = df[query_token]

            # IDF component
            idf = math.log((num_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

            # TF component with length normalization
            numerator = tf * (K1 + 1)
            denominator = tf + K1 * (1 - B + B * (doc_len / avg_doc_len))

            score += idf * (numerator / denominator)

        if score > 0:
            scores[idx] = score

    return scores
