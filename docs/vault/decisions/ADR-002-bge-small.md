---
project: contextos
type: adr
status: approved
owner: core-team
updated_at: 2026-06-03
tags:
  - embeddings
  - bge-small
  - decisions
---

# ADR-002: Use BAAI/bge-small-en-v1.5 for Embeddings

## Status
Approved

## Context
Need a local embedding model: no API key, CPU-only, small download, good quality.

## Decision
`BAAI/bge-small-en-v1.5` via sentence-transformers. 384 dimensions. ~130MB download. CPU inference. Downloaded once to `.contextos/embeddings/`, then `local_files_only=True`.

## Critical Implementation Notes
- Model saved to: `.contextos/embeddings/BAAI_bge-small-en-v1.5/`
- After save: `SentenceTransformer(str(model_path), local_files_only=True)`
- `normalize_embeddings=True` — vectors are L2-normalized for cosine similarity
- Batch size: 32 for CPU efficiency
- Dimension: exactly 384 — must match LanceDB schema
