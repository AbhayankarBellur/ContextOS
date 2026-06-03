"""
ContextOS compressor.py — Extractive context compression.
Uses TF-IDF sentence scoring (sumy) — no LLM, no network, fully local.
Triggered when assembled context exceeds token budget by more than THRESHOLD.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

COMPRESSION_THRESHOLD = 0.20   # trigger if over-budget by 20%
DEFAULT_RATIO = 0.60           # keep 60% of sentences by default


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def compress_text(text: str, ratio: float = DEFAULT_RATIO, language: str = "english") -> str:
    """
    Compress text using TF-IDF extractive summarisation.
    Keeps the top `ratio` fraction of sentences by importance score.
    Falls back to simple truncation if sumy is unavailable.
    """
    if not text.strip():
        return text

    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.lsa import LsaSummarizer
        from sumy.nlp.stemmers import Stemmer
        from sumy.utils import get_stop_words

        # Count sentences in source
        from sumy.parsers.plaintext import PlaintextParser
        parser = PlaintextParser.from_string(text, Tokenizer(language))
        total_sentences = len(list(parser.document.sentences))

        if total_sentences <= 3:
            return text   # too short to compress meaningfully

        keep_n = max(2, int(total_sentences * ratio))

        stemmer = Stemmer(language)
        summarizer = LsaSummarizer(stemmer)
        summarizer.stop_words = get_stop_words(language)

        sentences = summarizer(parser.document, keep_n)
        return " ".join(str(s) for s in sentences)

    except ImportError:
        logger.debug("sumy not available — falling back to truncation")
        # Simple fallback: keep first ratio% of characters
        keep_chars = int(len(text) * ratio)
        return text[:keep_chars] + "…"
    except Exception as exc:
        logger.debug("Compression failed (%s) — returning original", exc)
        return text


def compress_context_chunks(
    chunks: list[dict],
    max_tokens: int,
    ratio: float = DEFAULT_RATIO,
) -> tuple[list[dict], bool]:
    """
    Compress chunk content if total token estimate exceeds max_tokens * (1 + THRESHOLD).
    Returns (possibly_compressed_chunks, was_compressed).

    Each chunk dict must have a "content" key.
    """
    total = sum(_estimate_tokens(c.get("content", "")) for c in chunks)
    budget_with_margin = max_tokens * (1 + COMPRESSION_THRESHOLD)

    if total <= budget_with_margin:
        return chunks, False

    compressed = []
    for chunk in chunks:
        content = chunk.get("content", "")
        new_content = compress_text(content, ratio=ratio)
        compressed.append({**chunk, "content": new_content})

    logger.info(
        "Compression applied: %d → %d estimated tokens",
        total,
        sum(_estimate_tokens(c.get("content", "")) for c in compressed),
    )
    return compressed, True
