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
