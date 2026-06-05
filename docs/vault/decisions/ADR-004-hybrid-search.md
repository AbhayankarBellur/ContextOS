---
project: contextos
type: adr
status: approved
owner: core-team
updated_at: 2026-06-04
tags:
  - retrieval
  - hybrid-search
  - bm25
  - decisions
---

# ADR-004: Hybrid Search (BM25 + Vector with RRF)

## Status
Approved

## Context
Vector-only cosine similarity retrieval misses exact keyword matches. A developer searching for "BookingService.create_booking" gets poor results because the embedding model generalises the query semantically rather than matching the exact symbol name. Hybrid retrieval combines the semantic strength of vectors with the precision of BM25 keyword matching.

## Decision
Implement hybrid search using BM25Okapi (rank-bm25 library) alongside existing LanceDB vector search. Merge ranked lists using Reciprocal Rank Fusion (RRF) with configurable alpha weight.

### Algorithm
```
score(doc) = alpha * (1/(k + rank_vector)) + (1-alpha) * (1/(k + rank_bm25))
k = 60  (RRF smoothing constant)
alpha = 0.7  (default: vector-weighted)
```

### Implementation
- `store.hybrid_search(query_text, query_vector, alpha=0.7)` — new method
- `store._bm25_search(query_text)` — BM25Okapi on in-memory corpus
- `store._rrf_merge(vector_results, bm25_results)` — RRF fusion
- `retrieval.search()` uses hybrid by default; falls back to vector-only
- Config: `hybrid_search: true`, `hybrid_alpha: 0.7` in `.contextos/config.yaml`

## Consequences
**Positive:**
- 30-50% improvement in retrieval for exact name/symbol queries
- Better handling of technical terms, acronyms, and code identifiers
- RRF is parameter-light and robust across query types
- rank-bm25 is a lightweight pure-Python dependency

**Negative:**
- BM25 loads full corpus into memory on each query (acceptable for <100K chunks)
- Slightly higher latency (~50ms overhead on first BM25 call)
- `numpy` required for argsort (already a transitive dependency)

## Alternatives Considered
- Pure LanceDB FTS: available but less control over fusion weighting
- Cross-encoder re-ranking: higher quality but requires a second model download
- BM25 only: rejected — loses semantic understanding for paraphrase queries
