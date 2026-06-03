"""
ContextOS chunker.py — Markdown chunking using LangChain MarkdownHeaderTextSplitter.
Chunks at H1/H2/H3 boundaries. No LLM dependency.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from langchain_text_splitters import MarkdownHeaderTextSplitter

from contextos.schema import Chunk, Document

logger = logging.getLogger(__name__)

MIN_TOKENS = 100
MAX_TOKENS = 500

# Headers to split on
HEADERS_TO_SPLIT_ON = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3"),
]


def _count_tokens(text: str) -> int:
    """Approximate token count by word count (no LLM dependency)."""
    return len(text.split())


def _make_chunk_id(doc_id: str, heading: str, index: int) -> str:
    raw = f"{doc_id}:{heading}:{index}"
    return hashlib.sha256(raw.encode()).hexdigest()


def chunk_document(doc: Document) -> list[Chunk]:
    """
    Split a Document into Chunks at Markdown header boundaries.
    - Merges chunks below MIN_TOKENS with the next sibling.
    - Chunks above MAX_TOKENS are left as-is (splitter handles naturally at headers).
    - Returns list of Chunk objects with empty embeddings (filled by embedder).
    """
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )

    try:
        splits = splitter.split_text(doc.content)
    except Exception as exc:
        logger.warning("Chunking failed for '%s': %s — treating as single chunk", doc.title, exc)
        splits = []

    # If no splits (no headers), treat whole content as one chunk
    if not splits:
        chunk_text = doc.content.strip()
        if not chunk_text:
            return []
        return [
            Chunk(
                id=_make_chunk_id(doc.id, "root", 0),
                doc_id=doc.id,
                heading=doc.title,
                content=chunk_text,
                embedding=[],
                token_count=_count_tokens(chunk_text),
            )
        ]

    # Build raw chunk list from splitter output
    raw_chunks: list[tuple[str, str]] = []  # (heading, content)
    for split in splits:
        # Extract the heading from metadata
        meta = split.metadata or {}
        heading_parts = [meta.get("H1", ""), meta.get("H2", ""), meta.get("H3", "")]
        heading = " > ".join(p for p in heading_parts if p) or doc.title
        content = split.page_content.strip()
        if content:
            raw_chunks.append((heading, content))

    if not raw_chunks:
        return []

    # Merge undersized chunks with their next sibling
    merged: list[tuple[str, str]] = []
    i = 0
    while i < len(raw_chunks):
        heading, content = raw_chunks[i]
        token_count = _count_tokens(content)

        if token_count < MIN_TOKENS and i + 1 < len(raw_chunks):
            # Merge with next
            next_heading, next_content = raw_chunks[i + 1]
            merged_content = content + "\n\n" + next_content
            merged.append((heading, merged_content))
            i += 2
        else:
            merged.append((heading, content))
            i += 1

    # Build Chunk objects
    chunks: list[Chunk] = []
    for idx, (heading, content) in enumerate(merged):
        chunks.append(
            Chunk(
                id=_make_chunk_id(doc.id, heading, idx),
                doc_id=doc.id,
                heading=heading,
                content=content,
                embedding=[],
                token_count=_count_tokens(content),
            )
        )

    return chunks


def chunk_all_documents(documents: list[Document], cache_dir: Path) -> dict[str, list[Chunk]]:
    """
    Chunk all documents. Writes chunks to cache_dir/<doc_id>.json.
    Returns mapping of doc_id -> list[Chunk].
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[Chunk]] = {}
    total_chunks = 0

    for doc in documents:
        chunks = chunk_document(doc)
        result[doc.id] = chunks
        total_chunks += len(chunks)

        # Write to cache
        cache_file = cache_dir / f"{doc.id}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump([c.model_dump() for c in chunks], f, indent=2)

    logger.info("Chunked %d documents into %d chunks", len(documents), total_chunks)
    return result


def load_chunks_from_cache(doc_id: str, cache_dir: Path) -> Optional[list[Chunk]]:
    """Load chunks for a document from cache."""
    cache_file = cache_dir / f"{doc_id}.json"
    if not cache_file.exists():
        return None
    with open(cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Chunk(**item) for item in data]
