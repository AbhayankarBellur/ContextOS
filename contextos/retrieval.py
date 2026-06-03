"""
ContextOS retrieval.py — Full retrieval pipeline.
Pipeline: metadata pre-filter → vector search → graph expansion → priority rerank → token budget → context assembly
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from contextos.schema import (
    GraphNode, SearchRequest, SearchResultItem, SearchResponse,
    ContextRequest, ContextResponse, DocumentType,
)

logger = logging.getLogger(__name__)

# Priority order for reranking (higher = more important)
PRIORITY_MAP = {
    "context":      1.0,
    "decisions":    0.9,
    "adr":          0.9,
    "architecture": 0.8,
    "domain":       0.7,
    "workflow":     0.6,
    "workflows":    0.6,
    "product":      0.5,
    "note":         0.3,
}


def _priority_boost(doc_type: str) -> float:
    return PRIORITY_MAP.get(doc_type.lower(), 0.4)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 chars."""
    return len(text) // 4


def search(
    query: str,
    embedder,
    store,
    graph_builder,
    project: Optional[str] = None,
    type_filter: Optional[str] = None,
    domain_filter: Optional[str] = None,
    limit: int = 5,
    include_graph: bool = False,
) -> SearchResponse:
    """
    Full search pipeline:
    1. Embed query
    2. Metadata pre-filter + vector search
    3. Optional graph expansion
    4. Return ranked results
    """
    t0 = time.time()

    # Step 1: Embed query
    query_vec = embedder.embed_query(query)

    # Step 2: Vector search with pre-filter
    raw_results = store.search(
        query_vector=query_vec,
        project=project,
        type_filter=type_filter,
        domain_filter=domain_filter,
        limit=limit * 2,  # over-fetch for reranking
    )

    # Step 3: Build result items
    result_items = []
    for r in raw_results:
        # LanceDB returns _distance (L2). Convert to similarity.
        distance = float(r.get("_distance", 1.0))
        score = max(0.0, 1.0 - distance)

        # Apply priority boost
        doc_type = r.get("type", "note")
        boosted_score = score * (0.7 + 0.3 * _priority_boost(doc_type))

        # Graph expansion
        neighbours: list[GraphNode] = []
        if include_graph and graph_builder and graph_builder.graph:
            neighbours = graph_builder.expand([r.get("doc_id", "")], hops=1)

        result_items.append(SearchResultItem(
            doc_id=r.get("doc_id", ""),
            title=r.get("title", ""),
            filepath=r.get("filepath", ""),
            type=DocumentType(doc_type) if doc_type in DocumentType.__members__ else DocumentType.note,
            domain=r.get("domain") or None,
            score=round(boosted_score, 4),
            chunk=r.get("content", ""),
            graph_neighbours=neighbours,
        ))

    # Sort by boosted score, trim to limit
    result_items.sort(key=lambda x: x.score, reverse=True)
    result_items = result_items[:limit]

    latency_ms = int((time.time() - t0) * 1000)
    return SearchResponse(results=result_items, latency_ms=latency_ms)


def assemble_context(
    query: str,
    embedder,
    store,
    graph_builder,
    project: Optional[str] = None,
    max_tokens: int = 4000,
    priority_order: Optional[list[str]] = None,
) -> ContextResponse:
    """
    Assemble a ready-to-paste context block for an agent.
    1. Search for relevant chunks
    2. Rerank by priority order
    3. Greedily pack into token budget
    4. Format as Markdown with section headers
    """
    if priority_order is None:
        priority_order = ["context", "adr", "architecture", "domain", "workflow", "product"]

    # Build priority lookup
    priority_lookup = {t: (len(priority_order) - i) for i, t in enumerate(priority_order)}

    # Fetch more candidates than we need, we'll budget-trim
    query_vec = embedder.embed_query(query)
    raw_results = store.search(
        query_vector=query_vec,
        project=project,
        limit=30,
    )

    if not raw_results:
        return ContextResponse(context="No relevant context found.", sources=[], token_estimate=0)

    # Score and sort with priority boost
    scored = []
    for r in raw_results:
        distance = float(r.get("_distance", 1.0))
        base_score = max(0.0, 1.0 - distance)
        doc_type = r.get("type", "note")
        priority = priority_lookup.get(doc_type, 0)
        final_score = base_score * 0.6 + (priority / len(priority_order)) * 0.4
        scored.append((final_score, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Greedy token budget packing
    used_tokens = 0
    selected = []
    seen_docs = {}  # doc_id -> list of chunks

    for score, result in scored:
        content = result.get("content", "")
        heading = result.get("heading", "")
        doc_id = result.get("doc_id", "")
        title = result.get("title", "Unknown")

        chunk_text = f"### {heading}\n\n{content}" if heading and heading != title else content
        chunk_tokens = _estimate_tokens(chunk_text)

        if used_tokens + chunk_tokens > max_tokens:
            continue

        if doc_id not in seen_docs:
            seen_docs[doc_id] = {
                "title": title,
                "type": result.get("type", ""),
                "domain": result.get("domain", ""),
                "filepath": result.get("filepath", ""),
                "chunks": [],
            }

        seen_docs[doc_id]["chunks"].append(chunk_text)
        used_tokens += chunk_tokens
        selected.append(result)

        if used_tokens >= max_tokens:
            break

    # Format context Markdown
    sections: list[str] = []

    # Group by type in priority order
    type_to_docs = {}
    for doc_id, doc_info in seen_docs.items():
        t = doc_info["type"]
        if t not in type_to_docs:
            type_to_docs[t] = []
        type_to_docs[t].append((doc_id, doc_info))

    section_headers = {
        "context":      "## Current Context",
        "adr":          "## Architecture Decisions",
        "architecture": "## Architecture",
        "domain":       "## Domain Models",
        "workflow":     "## Workflows",
        "product":      "## Product",
        "note":         "## Notes",
    }

    for type_name in priority_order + [t for t in type_to_docs if t not in priority_order]:
        if type_name not in type_to_docs:
            continue
        header = section_headers.get(type_name, f"## {type_name.title()}")
        sections.append(header)
        for doc_id, doc_info in type_to_docs[type_name]:
            sections.append(f"\n### {doc_info['title']}")
            for chunk in doc_info["chunks"]:
                sections.append(chunk)

    context_text = "\n\n".join(sections)
    token_estimate = _estimate_tokens(context_text)

    # Apply compression if over budget
    compressed = False
    if token_estimate > max_tokens:
        try:
            from contextos.compressor import compress_text
            context_text = compress_text(context_text, ratio=max_tokens / token_estimate)
            token_estimate = _estimate_tokens(context_text)
            compressed = True
        except Exception as exc:
            logger.debug("Compression skipped: %s", exc)

    sources = [
        {
            "title": doc_info["title"],
            "filepath": doc_info["filepath"],
            "type": doc_info["type"],
            "domain": doc_info.get("domain", ""),
        }
        for doc_id, doc_info in seen_docs.items()
    ]

    return ContextResponse(
        context=context_text,
        sources=sources,
        token_estimate=token_estimate,
    )
