---
project: contextos
type: adr
status: approved
owner: core-team
updated_at: 2026-06-03
tags:
  - lancedb
  - vector-store
  - decisions
---

# ADR-001: Use LanceDB as the Embedded Vector Store

## Status
Approved

## Context
ContextOS requires a vector store that is: fully embedded (no Docker, no server), runs on local filesystem, supports metadata pre-filtering, and has a Python API.

## Decision
Use LanceDB 0.6+. Store at `.contextos/lancedb/`. Connect with `lancedb.connect(str(path))`.

## Consequences
**Positive:** Zero infrastructure. No Docker. Metadata pre-filter before vector search. Apache Arrow columnar storage. Fast incremental upserts.

**Negative:** Relatively new library. Embedding column must be a fixed-length `list_(float32, 384)` — this must match the model dimension exactly.

## Critical Implementation Notes
- Schema: `pa.field("embedding", pa.list_(pa.float32(), 384))` — dimension is fixed at 384 for bge-small
- Delete before upsert: `table.delete(f"doc_id = '{doc_id}'")`  then `table.add(records)`
- Never use a cloud URI — always a local directory path string
