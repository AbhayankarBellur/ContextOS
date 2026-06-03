---
project: contextos
type: workflow
domain: indexing
status: approved
owner: core-team
updated_at: 2026-06-03
tags:
  - indexing
  - workflow
  - embeddings
---

# Indexing Flow (context index)

## End-to-End Steps

### Step 1 — Load Registry
`vault.load_registry(metadata_dir)` reads `.contextos/metadata/registry.json`.
If empty: prompt user to run `context import <path>` first.

### Step 2 — Build Document Objects
For each registry record, read the file from disk into a `Document` object.
Skip missing files with a warning.

### Step 3 — Chunk Documents
`chunker.chunk_all_documents(documents, cache_dir)`
Uses `MarkdownHeaderTextSplitter` at H1/H2/H3.
Writes chunks to `.contextos/cache/<doc_id>.json`.
Returns `dict[doc_id -> list[Chunk]]`.

### Step 4 — Generate Embeddings
`embedder.embed_chunks_with_progress(chunks_by_doc, embedder)`
Batches of 32. Rich progress bar.
Each `Chunk.embedding` is filled with a 384-dim float list.

### Step 5 — Write to LanceDB
`store.upsert_chunks(all_chunks, doc_map)`
Deletes existing chunks for each doc_id, then bulk-inserts.
Writes `.contextos/lancedb/`.

### Step 6 — Build Knowledge Graph
`graph.GraphBuilder().build(documents)`
Nodes: one per document. Edges: from tags, domain relationships, ADR supersedes.
Saves to `.contextos/graph/graph.json`.

### Step 7 — Write Index Metadata
Writes `.contextos/metadata/index_meta.json` with timestamp, counts, model name.

## Idempotency
`context index` is safe to run multiple times. It rebuilds from the current vault state. Future optimization: skip unchanged files by content hash.
