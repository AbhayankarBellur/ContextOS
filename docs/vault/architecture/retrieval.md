---
project: contextos
type: architecture
domain: retrieval
status: approved
owner: core-team
updated_at: 2026-06-03
tags:
  - retrieval
  - pipeline
  - embeddings
  - lancedb
---

# Retrieval Pipeline

## Pipeline Steps (in order)

1. **Embed query** — `Embedder.embed_query(text)` → 384-dim float vector
2. **Metadata pre-filter** — filter LanceDB by `project`, `type`, `domain` before vector search
3. **Cosine similarity search** — LanceDB returns top-K by L2 distance (distance = 1 - similarity)
4. **Priority rerank** — boost scores by document type priority:
   - context: 1.0 · adr: 0.9 · architecture: 0.8 · domain: 0.7 · workflow: 0.6 · product: 0.5
5. **Graph expansion** — if `include_graph=True`, fetch 1-hop NetworkX neighbours
6. **Token budget packing** — greedily pack chunks into `max_tokens` (default 4000)
7. **Context assembly** — format as Markdown with section headers per document type

## Score Calculation

```python
distance = result["_distance"]           # LanceDB L2 distance
base_score = max(0.0, 1.0 - distance)   # Convert to similarity
boosted = base_score * (0.7 + 0.3 * priority_boost(doc_type))
```

## Chunking Strategy

- Splitter: `LangChain MarkdownHeaderTextSplitter` at H1, H2, H3
- Min chunk: 100 tokens (merged with next sibling if below)
- Max chunk: 500 tokens
- Chunk ID: `sha256(doc_id + heading + index)`
- Each chunk carries full parent document metadata (denormalized in LanceDB)

## Performance Targets

| Metric | Target |
|---|---|
| Search P95 | < 500ms for 1000-doc vault |
| Context assembly | < 1s end-to-end |
| Graph query | < 300ms |
| Index (incremental) | Only re-index changed files by content hash |
