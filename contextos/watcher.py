"""
ContextOS watcher.py — Live filesystem watcher for vault auto-re-indexing.
Uses watchfiles (already a uvicorn dependency) — no extra install needed.
Runs as a background thread alongside context serve --watch.

Only re-indexes the specific changed file, not the whole vault.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Debounce: wait this many seconds after last change before re-indexing
DEBOUNCE_SECONDS = 2.0


class VaultWatcher:
    """
    Watches registered vault paths for .md file changes.
    On change: re-chunks, re-embeds, and upserts only the changed file.
    Runs in a background daemon thread.
    """

    def __init__(self, vault_paths: list[Path], config, on_reindex: Optional[Callable] = None):
        self.vault_paths = vault_paths
        self.config = config
        self.on_reindex = on_reindex  # optional callback after re-index
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pending: dict[str, float] = {}  # path -> last_change_timestamp
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the watcher in a background daemon thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ContextOS-Watcher")
        self._thread.start()
        logger.info("Vault watcher started for %d paths", len(self.vault_paths))

    def stop(self) -> None:
        """Signal the watcher to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Vault watcher stopped")

    def _run(self) -> None:
        """Main watcher loop using watchfiles."""
        try:
            from watchfiles import watch, Change
        except ImportError:
            logger.warning("watchfiles not available — vault watch disabled")
            return

        watch_paths = [str(p) for p in self.vault_paths if p.exists()]
        if not watch_paths:
            logger.warning("No valid vault paths to watch")
            return

        logger.info("Watching: %s", watch_paths)

        try:
            for changes in watch(*watch_paths, stop_event=self._stop_event, yield_on_timeout=True, poll_delay_ms=500):
                if self._stop_event.is_set():
                    break
                if not changes:
                    # Timeout — process any debounced pending changes
                    self._flush_pending()
                    continue

                for change_type, path in changes:
                    if not path.endswith(".md"):
                        continue
                    if change_type in (Change.added, Change.modified):
                        with self._lock:
                            self._pending[path] = time.time()
                        logger.debug("Change detected: %s %s", change_type, path)
                    elif change_type == Change.deleted:
                        logger.info("Vault file deleted: %s (run context index to update)", path)

                self._flush_pending()

        except Exception as exc:
            if not self._stop_event.is_set():
                logger.error("Watcher error: %s", exc)

    def _flush_pending(self) -> None:
        """Process debounced pending changes."""
        now = time.time()
        to_process = []

        with self._lock:
            for path, ts in list(self._pending.items()):
                if now - ts >= DEBOUNCE_SECONDS:
                    to_process.append(path)
                    del self._pending[path]

        for path in to_process:
            self._reindex_file(Path(path))

    def _reindex_file(self, filepath: Path) -> None:
        """Re-index a single changed file."""
        t0 = time.time()
        logger.info("Re-indexing changed file: %s", filepath.name)

        try:
            from contextos.vault import parse_document, load_registry, write_registry
            from contextos.chunker import chunk_document
            from contextos.embedder import Embedder
            from contextos.store import VectorStore
            from contextos.schema import Document

            cfg = self.config

            # Find vault root for this file
            vault_root = None
            for vp in self.vault_paths:
                try:
                    filepath.relative_to(vp)
                    vault_root = vp
                    break
                except ValueError:
                    continue

            if vault_root is None:
                logger.warning("Cannot determine vault root for %s", filepath)
                return

            # Parse the changed document
            doc = parse_document(filepath, vault_root)
            if doc is None:
                logger.warning("Failed to parse %s", filepath)
                return

            # Chunk
            chunks = chunk_document(doc)
            if not chunks:
                logger.debug("No chunks from %s", filepath.name)
                return

            # Embed
            embedder = Embedder(cfg.embeddings_dir)
            texts = [c.content for c in chunks]
            vectors = embedder.embed(texts)
            for chunk, vec in zip(chunks, vectors):
                chunk.embedding = vec

            # Upsert to LanceDB
            store = VectorStore(cfg.lancedb_dir)
            written = store.upsert_chunks(chunks, {doc.id: doc})

            elapsed = time.time() - t0
            logger.info(
                "Re-indexed %s: %d chunks in %.2fs",
                filepath.name, written, elapsed
            )

            # Update hash store for this file
            from contextos.vault import update_hash_store
            update_hash_store(cfg.metadata_dir, [doc])

            # Call optional callback (e.g., update server state)
            if self.on_reindex:
                self.on_reindex(doc, chunks)

        except Exception as exc:
            logger.error("Failed to re-index %s: %s", filepath, exc)


# Module-level singleton — started by api.py when watch=True
_watcher: Optional[VaultWatcher] = None


def start_watcher(config) -> VaultWatcher:
    """Start the global vault watcher. Called by context serve --watch."""
    global _watcher
    if _watcher is not None:
        _watcher.stop()
    _watcher = VaultWatcher(vault_paths=config.vault_paths, config=config)
    _watcher.start()
    return _watcher


def stop_watcher() -> None:
    """Stop the global vault watcher."""
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None


def watcher_status() -> dict:
    """Return watcher status for health checks."""
    if _watcher is None:
        return {"active": False}
    return {
        "active":      True,
        "vault_paths": [str(p) for p in _watcher.vault_paths],
        "pending":     len(_watcher._pending),
    }
