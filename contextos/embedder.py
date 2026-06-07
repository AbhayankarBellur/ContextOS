"""
ContextOS embedder.py — sentence-transformers wrapper.
Model: BAAI/bge-small-en-v1.5 (384-dim, local CPU, no API).
Downloads once to .contextos/embeddings/, then local_files_only=True.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
BATCH_SIZE = 32


class Embedder:
    """
    Wraps sentence-transformers SentenceTransformer.
    - First run: downloads model to cache_dir (~130MB, one-time).
    - Subsequent runs: local_files_only=True — fully offline.
    - CPU inference only. No GPU required.
    """

    def __init__(self, cache_dir: Path, model_name: str = EMBEDDING_MODEL):
        self.cache_dir = cache_dir
        self.model_name = model_name
        self._model = None
        self.dim = 384
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_model(self) -> None:
        """Lazy-load the model. Uses HuggingFace cache; saves a local copy for offline use."""
        if self._model is not None:
            return

        import os
        import logging as _logging
        # Suppress noisy progress output from transformers/tokenizers
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        _logging.getLogger("sentence_transformers").setLevel(_logging.ERROR)
        _logging.getLogger("transformers").setLevel(_logging.ERROR)

        from sentence_transformers import SentenceTransformer
        import contextlib, io

        local_copy = self.cache_dir / self.model_name.replace("/", "_")

        # Option 1: local copy saved by us
        if local_copy.exists() and any(local_copy.iterdir()):
            logger.info("Loading model from local copy: %s", local_copy)
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    self._model = SentenceTransformer(str(local_copy))
                return
            except Exception as exc:
                logger.warning("Local copy load failed (%s) — loading from HF cache", exc)

        # Option 2: load from HF cache / download
        logger.info("Loading model '%s' (downloading if needed)…", self.model_name)
        with contextlib.redirect_stderr(io.StringIO()):
            self._model = SentenceTransformer(self.model_name)

        # Store actual embedding dimension
        try:
            self.dim = self._model.get_embedding_dimension()
        except AttributeError:
            try:
                self.dim = self._model.get_sentence_embedding_dimension()
            except Exception:
                self.dim = 384

        # Save a local copy for explicit offline tracking
        try:
            self._model.save(str(local_copy))
            logger.info("Model local copy saved to %s", local_copy)
        except Exception as exc:
            logger.debug("Could not save local copy: %s", exc)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts. Returns list of 384-dim float vectors.
        Processes in batches of BATCH_SIZE.
        """
        self._load_model()
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            vectors = self._model.encode(
                batch,
                normalize_embeddings=True,  # cosine similarity ready
                show_progress_bar=False,
            )
            all_embeddings.extend(v.tolist() for v in vectors)

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        results = self.embed([text])
        return results[0] if results else []

    def warmup(self) -> None:
        """Pre-load the embedding model in a background thread to eliminate cold-start latency."""
        import threading
        def _load():
            try:
                self._load_model()
            except Exception as exc:
                logger.debug("Warmup failed: %s", exc)
        t = threading.Thread(target=_load, daemon=True, name="ContextOS-EmbedderWarmup")
        t.start()


def embed_chunks_with_progress(
    chunks_by_doc: dict,  # doc_id -> list[Chunk]
    embedder: Embedder,
) -> dict:
    """
    Embed all chunks across all documents, with a rich progress bar.
    Updates Chunk.embedding in-place.
    Returns the same dict with embeddings filled in.
    """
    from contextos.schema import Chunk

    # Flatten to list for batch processing
    all_chunks: list[Chunk] = []
    for chunk_list in chunks_by_doc.values():
        all_chunks.extend(chunk_list)

    if not all_chunks:
        logger.warning("No chunks to embed")
        return chunks_by_doc

    total = len(all_chunks)
    logger.info("Embedding %d chunks...", total)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Embedding chunks..."),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("embed", total=total)

        texts = [c.content for c in all_chunks]
        for i in range(0, total, BATCH_SIZE):
            batch_texts = texts[i : i + BATCH_SIZE]
            batch_chunks = all_chunks[i : i + BATCH_SIZE]
            vectors = embedder.embed(batch_texts)
            for chunk, vec in zip(batch_chunks, vectors):
                chunk.embedding = vec
            progress.advance(task, len(batch_chunks))

    return chunks_by_doc
