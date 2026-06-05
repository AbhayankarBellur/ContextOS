"""
ContextOS store.py — LanceDB vector store (read/write).
All data stored locally in .contextos/lancedb/. No cloud URI. No Docker.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pyarrow as pa

from contextos.schema import Chunk, Document, DocumentType

logger = logging.getLogger(__name__)

TABLE_NAME = "chunks"


def _chunk_to_record(chunk: Chunk, doc: Optional[Document] = None) -> dict:
    """Convert a Chunk (with embedding) to a flat dict for LanceDB."""
    return {
        "id": chunk.id,
        "doc_id": chunk.doc_id,
        "heading": chunk.heading,
        "content": chunk.content,
        "embedding": chunk.embedding,
        "token_count": chunk.token_count,
        # Document metadata (denormalized for fast filtering)
        "project": doc.project if doc else "",
        "type": doc.type.value if doc else "",
        "domain": doc.domain or "" if doc else "",
        "status": doc.status.value if doc else "",
        "title": doc.title if doc else "",
        "filepath": str(doc.filepath) if doc else "",
        "tags": json.dumps(doc.tags) if doc else "[]",
    }


class VectorStore:
    """LanceDB-backed vector store for ContextOS chunks."""

    def __init__(self, lancedb_dir: Path):
        self.lancedb_dir = lancedb_dir
        self.lancedb_dir.mkdir(parents=True, exist_ok=True)
        self._db = None
        self._table = None

    def _open(self):
        """Lazy-open LanceDB connection."""
        if self._db is None:
            import lancedb
            self._db = lancedb.connect(str(self.lancedb_dir))

    def _get_table(self):
        """Get or create the chunks table."""
        self._open()
        if TABLE_NAME in self._db.table_names():
            return self._db.open_table(TABLE_NAME)
        return None

    def upsert_chunks(self, chunks: list[Chunk], documents: dict[str, Document]) -> int:
        """
        Write chunks with embeddings to LanceDB.
        Uses merge/overwrite based on chunk id.
        Returns number of chunks written.
        """
        self._open()

        if not chunks:
            return 0

        # Filter to only chunks that have embeddings
        ready = [c for c in chunks if c.embedding]
        if not ready:
            logger.warning("No chunks with embeddings to write")
            return 0

        records = []
        for chunk in ready:
            doc = documents.get(chunk.doc_id)
            records.append(_chunk_to_record(chunk, doc))

        import lancedb
        from lancedb.pydantic import Vector
        import pyarrow as pa

        # Build schema
        schema = pa.schema([
            pa.field("id", pa.utf8()),
            pa.field("doc_id", pa.utf8()),
            pa.field("heading", pa.utf8()),
            pa.field("content", pa.utf8()),
            pa.field("embedding", pa.list_(pa.float32(), 384)),
            pa.field("token_count", pa.int32()),
            pa.field("project", pa.utf8()),
            pa.field("type", pa.utf8()),
            pa.field("domain", pa.utf8()),
            pa.field("status", pa.utf8()),
            pa.field("title", pa.utf8()),
            pa.field("filepath", pa.utf8()),
            pa.field("tags", pa.utf8()),
        ])

        if TABLE_NAME not in self._db.table_names():
            table = self._db.create_table(TABLE_NAME, data=records, schema=schema)
            logger.info("Created LanceDB table '%s' with %d chunks", TABLE_NAME, len(records))
        else:
            table = self._db.open_table(TABLE_NAME)
            # Delete existing chunks for these doc_ids to allow re-index
            doc_ids = list({c.doc_id for c in ready})
            for doc_id in doc_ids:
                try:
                    table.delete(f"doc_id = '{doc_id}'")
                except Exception:
                    pass
            table.add(records)
            logger.info("Upserted %d chunks to LanceDB", len(records))

        return len(records)

    def search(
        self,
        query_vector: list[float],
        project: Optional[str] = None,
        type_filter: Optional[str] = None,
        domain_filter: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Cosine similarity search with optional metadata pre-filters.
        Returns list of result dicts with score and metadata.
        """
        table = self._get_table()
        if table is None:
            logger.warning("No LanceDB table found — run 'context index' first")
            return []

        try:
            query = table.search(query_vector, vector_column_name="embedding")

            # Apply metadata pre-filters
            filters = []
            if project:
                filters.append(f"project = '{project}'")
            if type_filter:
                filters.append(f"type = '{type_filter}'")
            if domain_filter:
                filters.append(f"domain = '{domain_filter}'")

            if filters:
                query = query.where(" AND ".join(filters), prefilter=True)

            results = query.limit(limit).to_list()
            return results

        except Exception as exc:
            logger.error("Search failed: %s", exc)
            return []

    def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float],
        project: Optional[str] = None,
        type_filter: Optional[str] = None,
        domain_filter: Optional[str] = None,
        limit: int = 5,
        alpha: float = 0.7,
    ) -> list[dict]:
        """
        Hybrid search: combines vector similarity with BM25 keyword search.
        Uses Reciprocal Rank Fusion (RRF) to merge ranked lists.
        alpha controls vector weight (0.0 = BM25 only, 1.0 = vector only).

        Falls back to vector-only search if BM25 fails.
        """
        # Get more candidates for fusion
        fetch_n = min(limit * 4, 50)

        # --- Vector search ---
        vector_results = self.search(
            query_vector=query_vector,
            project=project,
            type_filter=type_filter,
            domain_filter=domain_filter,
            limit=fetch_n,
        )

        if not vector_results or alpha >= 0.99:
            return vector_results[:limit]

        # --- BM25 keyword search ---
        bm25_results = self._bm25_search(
            query_text=query_text,
            project=project,
            type_filter=type_filter,
            domain_filter=domain_filter,
            limit=fetch_n,
        )

        if not bm25_results:
            # BM25 returned nothing — fall back to vector-only results
            return vector_results[:limit]

        if alpha <= 0.01:
            return bm25_results[:limit]

        # --- Reciprocal Rank Fusion ---
        return self._rrf_merge(vector_results, bm25_results, limit=limit, alpha=alpha)

    def _bm25_search(
        self,
        query_text: str,
        project: Optional[str] = None,
        type_filter: Optional[str] = None,
        domain_filter: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """BM25 keyword search over chunk content using rank_bm25."""
        table = self._get_table()
        if table is None:
            return []
        try:
            from rank_bm25 import BM25Okapi

            df = table.to_pandas()

            # Apply same metadata filters
            if project:
                df = df[df["project"] == project]
            if type_filter:
                df = df[df["type"] == type_filter]
            if domain_filter:
                df = df[df["domain"] == domain_filter]

            if df.empty:
                return []

            # Tokenise corpus
            corpus  = df["content"].fillna("").tolist()
            tokenised = [doc.lower().split() for doc in corpus]
            bm25   = BM25Okapi(tokenised)
            scores = bm25.get_scores(query_text.lower().split())

            # Get top-limit indices by score
            import numpy as np
            top_indices = np.argsort(scores)[::-1][:limit]

            results = []
            for idx in top_indices:
                if scores[idx] <= 0:
                    break
                row = df.iloc[idx].to_dict()
                row["_bm25_score"] = float(scores[idx])
                results.append(row)
            return results

        except Exception as exc:
            logger.debug("BM25 search failed: %s", exc)
            return []

    @staticmethod
    def _rrf_merge(
        vector_results: list[dict],
        bm25_results: list[dict],
        limit: int,
        alpha: float = 0.7,
        k: int = 60,
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion with weighted alpha.
        score = alpha * (1/(k+rank_vector)) + (1-alpha) * (1/(k+rank_bm25))
        """
        id_to_result: dict[str, dict] = {}
        vector_scores: dict[str, float] = {}
        bm25_scores:   dict[str, float] = {}

        for rank, r in enumerate(vector_results, 1):
            cid = r.get("id", str(rank))
            id_to_result[cid] = r
            vector_scores[cid] = 1.0 / (k + rank)

        for rank, r in enumerate(bm25_results, 1):
            cid = r.get("id", str(rank))
            if cid not in id_to_result:
                id_to_result[cid] = r
            bm25_scores[cid] = 1.0 / (k + rank)

        # Compute fused scores
        fused: dict[str, float] = {}
        for cid in id_to_result:
            vs = vector_scores.get(cid, 0.0)
            bs = bm25_scores.get(cid, 0.0)
            fused[cid] = alpha * vs + (1 - alpha) * bs

        # Sort by fused score, return top-limit
        sorted_ids = sorted(fused, key=lambda x: fused[x], reverse=True)[:limit]
        results = []
        for cid in sorted_ids:
            r = dict(id_to_result[cid])
            r["_rrf_score"] = fused[cid]
            results.append(r)
        return results

    def count_documents(self) -> int:
        """Return number of unique documents indexed."""
        table = self._get_table()
        if table is None:
            return 0
        try:
            df = table.to_pandas()[["doc_id"]].drop_duplicates()
            return len(df)
        except Exception:
            return 0

    def list_documents(
        self,
        project: Optional[str] = None,
        type_filter: Optional[str] = None,
        domain_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> list[dict]:
        """List unique documents from the index with optional filters."""
        table = self._get_table()
        if table is None:
            return []
        try:
            df = table.to_pandas()
            if project:
                df = df[df["project"] == project]
            if type_filter:
                df = df[df["type"] == type_filter]
            if domain_filter:
                df = df[df["domain"] == domain_filter]
            if status_filter:
                df = df[df["status"] == status_filter]

            # Deduplicate by doc_id, keep one row per doc
            df = df.drop_duplicates(subset=["doc_id"])
            cols = ["doc_id", "title", "type", "domain", "status", "project", "filepath"]
            return df[cols].to_dict(orient="records")
        except Exception as exc:
            logger.error("List documents failed: %s", exc)
            return []
