"""Book contradiction detection - lexical opposition detection between sources.

Extracted from book.py to reduce file size and isolate contradiction logic.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Constants for contradiction detection
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_CONTRADICTION_SENTENCE_CHARS = 40
_MIN_SHARED_TERM_CHARS = 4
_NEGATION_LOOKBACK_TOKENS = 5
_MAX_CONTRADICTIONS = 20

_NEGATION_MARKERS = frozenset(
    {
        "cannot",
        "fail",
        "failed",
        "fails",
        "false",
        "never",
        "no",
        "none",
        "not",
        "refute",
        "refuted",
        "refutes",
        "unsupported",
        "without",
    }
)

_COMMON_SHARED_TERMS = frozenset(
    {
        "about",
        "across",
        "after",
        "again",
        "among",
        "around",
        "because",
        "before",
        "behind",
        "being",
        "below",
        "between",
        "beyond",
        "could",
        "during",
        "first",
        "frontmatter",
        "index",
        "instead",
        "might",
        "should",
        "since",
        "still",
        "their",
        "there",
        "these",
        "those",
        "through",
        "under",
        "until",
        "where",
        "which",
        "while",
        "would",
    }
)

_PROVENANCE_SHARED_TERMS = frozenset(
    {
        "book",
        "draft",
        "evidence",
        "experiment",
        "finding",
        "node",
        "page",
        "result",
        "source",
        "study",
    }
)

_CONTRADICTION_IDIOMS = frozenset(
    {
        "question remains",
        "remains unclear",
        "remains open",
        "future work",
        "further investigation",
        "more research",
    }
)


def _strip_frontmatter(text: str) -> str:
    """Remove frontmatter block, return body only."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    return text[end + 5 :].lstrip()


def _is_structural_line(sentence: str) -> bool:
    """True if sentence is a structural element (header, list, code)."""
    return (
        sentence.startswith("#")
        or sentence.startswith("-")
        or sentence.startswith("*")
        or sentence.startswith(">")
        or sentence.startswith("```")
    )


def _sentence_candidates(text: str) -> list[str]:
    """Extract substantive claim sentences from page body."""
    body = _strip_frontmatter(text)
    body = re.sub(r"^>+\s?", "", body, flags=re.MULTILINE)
    sentences: list[str] = []
    for chunk in _SENTENCE_SPLIT_RE.split(body):
        sentence = " ".join(chunk.strip().split())
        if len(sentence) < _MIN_CONTRADICTION_SENTENCE_CHARS:
            continue
        if _is_structural_line(sentence):
            continue
        sentences.append(sentence)
    return sentences


def _tokens_for_sentence(sentence: str) -> list[str]:
    """Tokenize sentence with contraction normalization."""
    normalized = sentence.lower().replace("can't", "cannot").replace("won't", "not")
    normalized = re.sub(r"n't\b", " not", normalized)
    return _TOKEN_RE.findall(normalized)


def _shared_claim_terms(left_tokens: list[str], right_tokens: list[str]) -> list[str]:
    """Find substantive terms shared between two token lists."""

    def _is_subject(token: str) -> bool:
        return (
            len(token) >= _MIN_SHARED_TERM_CHARS
            and token not in _NEGATION_MARKERS
            and token not in _COMMON_SHARED_TERMS
            and token not in _PROVENANCE_SHARED_TERMS
            and not token.isdigit()
        )

    right_terms = {token for token in right_tokens if _is_subject(token)}
    seen: set[str] = set()
    terms: list[str] = []
    for token in left_tokens:
        if token in right_terms and token not in seen and _is_subject(token):
            seen.add(token)
            terms.append(token)
    return terms


def _negated_terms(tokens: list[str], terms: set[str]) -> set[str]:
    """Find which terms appear in a negation context."""
    negated: set[str] = set()
    for idx, token in enumerate(tokens):
        if token not in terms:
            continue
        start = max(0, idx - _NEGATION_LOOKBACK_TOKENS)
        if any(marker in _NEGATION_MARKERS for marker in tokens[start:idx]):
            negated.add(token)
    return negated


def _opposed_shared_terms(new_sentence: str, existing_sentence: str) -> list[str]:
    """Detect terms that appear negated in one sentence but not the other."""
    combined = f"{new_sentence}\n{existing_sentence}".lower()
    if any(idiom in combined for idiom in _CONTRADICTION_IDIOMS):
        return []
    new_tokens = _tokens_for_sentence(new_sentence)
    existing_tokens = _tokens_for_sentence(existing_sentence)
    shared_terms = _shared_claim_terms(new_tokens, existing_tokens)
    if not shared_terms:
        return []

    shared_set = set(shared_terms)
    new_negated = _negated_terms(new_tokens, shared_set)
    existing_negated = _negated_terms(existing_tokens, shared_set)
    return [term for term in shared_terms if (term in new_negated) != (term in existing_negated)]


def _detect_contradictions(
    port: int,
    slug: str,
    body: str,
    source_role: str,
) -> list[dict[str, object]]:
    """Find lexical contradictions between new source and existing book sources."""
    from minions.tools.book_helpers import _book_root

    source_dir = _book_root(port) / "sources"
    if not source_dir.exists():
        return []

    new_sentences = _sentence_candidates(body)
    if not new_sentences:
        return []

    contradictions: list[dict[str, object]] = []
    for page in sorted(source_dir.glob("*.md")):
        if page.name == f"{slug}.md":
            continue
        existing_sentences = _sentence_candidates(
            page.read_text(encoding="utf-8", errors="replace")
        )
        if not existing_sentences:
            continue
        for new_sentence in new_sentences:
            for existing_sentence in existing_sentences:
                shared_terms = _opposed_shared_terms(new_sentence, existing_sentence)
                if not shared_terms:
                    continue
                contradictions.append(
                    {
                        "opposing_page": f"book/sources/{page.name}",
                        "excerpts": {
                            "new": new_sentence,
                            "opposing": existing_sentence,
                        },
                        "shared_terms": shared_terms[:8],
                        "new_source": slug,
                        "new_source_role": source_role,
                    }
                )
                if len(contradictions) >= _MAX_CONTRADICTIONS:
                    return contradictions
                break
            if len(contradictions) >= _MAX_CONTRADICTIONS:
                return contradictions
    return contradictions


def _detect_contradictions_with_overlay(
    port: int,
    new_slug: str,
    new_body: str,
    source_role: str,
    *,
    overlay: dict[str, str],
) -> list[dict[str, Any]]:
    """Detect contradictions with in-memory overlay for batch processing."""
    base_results = _detect_contradictions(port, new_slug, new_body, source_role)
    if not overlay:
        return base_results

    new_sentences = _sentence_candidates(new_body)
    overlay_results: list[dict[str, Any]] = []
    for prior_slug, prior_body in overlay.items():
        if prior_slug == new_slug:
            continue
        prior_sentences = _sentence_candidates(prior_body)
        for new_sent in new_sentences:
            for prior_sent in prior_sentences:
                shared_terms = _opposed_shared_terms(new_sent, prior_sent)
                if shared_terms:
                    overlay_results.append(
                        {
                            "opposing_page": f"book/sources/{prior_slug}.md",
                            "shared_terms": shared_terms,
                            "excerpts": {"new": new_sent, "opposing": prior_sent},
                            "from_batch_overlay": True,
                        }
                    )
                    break
            else:
                continue
            break

    return base_results + overlay_results


__all__ = [
    "_detect_contradictions",
    "_detect_contradictions_with_overlay",
    "_opposed_shared_terms",
    "_sentence_candidates",
]
