"""
ContextOS memory.py — Memory management engine.
Handles disk usage analysis, project archiving, index purging, and space reclamation.
Never modifies vault documents — only operates on .contextos/ internal data.
"""
from __future__ import annotations
import json
import logging
import shutil
import tarfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _dir_size(path: Path) -> int:
    """Recursively sum file sizes under path in bytes."""
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _fmt_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_disk_breakdown(contextos_dir: Path) -> dict:
    """
    Return a detailed breakdown of disk usage inside .contextos/.
    Returns dict of {component: {"path": str, "size_bytes": int, "size_human": str}}.
    """
    components = {
        "lancedb":    contextos_dir / "lancedb",
        "embeddings": contextos_dir / "embeddings",
        "graph":      contextos_dir / "graph",
        "cache":      contextos_dir / "cache",
        "tokens":     contextos_dir / "tokens",
        "metadata":   contextos_dir / "metadata",
        "logs":       contextos_dir / "logs",
    }
    result = {}
    total = 0
    for name, path in components.items():
        size = _dir_size(path)
        total += size
        result[name] = {"path": str(path), "size_bytes": size, "size_human": _fmt_size(size)}
    result["_total"] = {"size_bytes": total, "size_human": _fmt_size(total)}
    return result


def get_projects_breakdown(contextos_dir: Path) -> list[dict]:
    """
    List all projects found in the LanceDB index with their chunk counts and estimated sizes.
    """
    lancedb_dir = contextos_dir / "lancedb"
    if not lancedb_dir.exists():
        return []
    try:
        import lancedb
        db = lancedb.connect(str(lancedb_dir))
        if "chunks" not in db.table_names():
            return []
        table = db.open_table("chunks")
        df = table.to_pandas()[["project", "doc_id"]].drop_duplicates()
        projects = []
        for project, group in df.groupby("project"):
            doc_count = group["doc_id"].nunique()
            projects.append({
                "project": project,
                "documents": doc_count,
                "chunks": len(table.to_pandas()[table.to_pandas()["project"] == project]),
            })
        return sorted(projects, key=lambda x: -x["documents"])
    except Exception as exc:
        logger.warning("Could not read project breakdown: %s", exc)
        return []


def purge_project(project_name: str, contextos_dir: Path) -> dict:
    """
    Remove all indexed data for a specific project from LanceDB and cache.
    Does NOT touch vault files.
    Returns {"deleted_chunks": int, "freed_bytes": int}.
    """
    lancedb_dir = contextos_dir / "lancedb"
    if not lancedb_dir.exists():
        return {"deleted_chunks": 0, "freed_bytes": 0}

    size_before = _dir_size(lancedb_dir)
    deleted = 0

    try:
        import lancedb
        db = lancedb.connect(str(lancedb_dir))
        if "chunks" in db.table_names():
            table = db.open_table("chunks")
            before = len(table.to_pandas())
            table.delete(f"project = '{project_name}'")
            after_df = table.to_pandas()
            after = len(after_df)
            deleted = before - after
    except Exception as exc:
        logger.error("Failed to purge project from LanceDB: %s", exc)

    # Also clear chunk cache files for this project
    cache_dir = contextos_dir / "cache"
    if cache_dir.exists():
        for f in cache_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data and isinstance(data, list) and data[0].get("doc_id", "").startswith(project_name[:8]):
                    f.unlink()
            except Exception:
                pass

    size_after = _dir_size(lancedb_dir)
    return {"deleted_chunks": deleted, "freed_bytes": max(0, size_before - size_after)}


def archive_project(project_name: str, contextos_dir: Path, archive_dir: Optional[Path] = None) -> Path:
    """
    Archive a project's index data to a compressed tarball.
    Keeps vault files intact. Removes the live index after archiving.
    Returns path to the archive file.
    """
    if archive_dir is None:
        archive_dir = contextos_dir / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    archive_path = archive_dir / f"{project_name}-{timestamp}.tar.gz"

    # Export project chunks to JSON first
    export_file = contextos_dir / f"_export_{project_name}.json"
    try:
        import lancedb
        db = lancedb.connect(str(contextos_dir / "lancedb"))
        if "chunks" in db.table_names():
            df = db.open_table("chunks").to_pandas()
            project_df = df[df["project"] == project_name]
            records = project_df.drop(columns=["embedding"], errors="ignore").to_dict(orient="records")
            export_file.write_text(json.dumps(records, indent=2))
    except Exception as exc:
        logger.error("Export failed: %s", exc)
        if not export_file.exists():
            export_file.write_text("[]")

    # Create tarball with export + metadata
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(export_file, arcname=f"{project_name}/chunks.json")
        meta_file = contextos_dir / "metadata" / "registry.json"
        if meta_file.exists():
            try:
                reg = json.loads(meta_file.read_text())
                project_reg = [r for r in reg if r.get("project") == project_name]
                tmp_reg = contextos_dir / f"_reg_{project_name}.json"
                tmp_reg.write_text(json.dumps(project_reg, indent=2))
                tar.add(tmp_reg, arcname=f"{project_name}/registry.json")
                tmp_reg.unlink()
            except Exception:
                pass
        graph_file = contextos_dir / "graph" / "graph.json"
        if graph_file.exists():
            tar.add(graph_file, arcname=f"{project_name}/graph.json")

    # Clean up temp file
    if export_file.exists():
        export_file.unlink()

    # Purge the live index for this project
    purge_project(project_name, contextos_dir)

    logger.info("Project '%s' archived to %s", project_name, archive_path)
    return archive_path


def clear_embeddings_cache(contextos_dir: Path) -> dict:
    """
    Remove the downloaded embedding model cache.
    Model will be re-downloaded on next index run.
    Returns {"freed_bytes": int}.
    """
    embeddings_dir = contextos_dir / "embeddings"
    size = _dir_size(embeddings_dir)
    if embeddings_dir.exists():
        shutil.rmtree(embeddings_dir)
        embeddings_dir.mkdir(parents=True, exist_ok=True)
    return {"freed_bytes": size, "size_human": _fmt_size(size)}


def reset_index(contextos_dir: Path, keep_tokens: bool = True) -> dict:
    """
    Full reset of .contextos/ index data.
    Wipes: lancedb, graph, cache, embeddings, metadata.
    Preserves: tokens (unless keep_tokens=False), config.yaml, archives.
    NEVER touches vault documents.
    """
    size_before = _dir_size(contextos_dir)
    to_clear = ["lancedb", "graph", "cache", "embeddings", "metadata", "logs"]
    if not keep_tokens:
        to_clear.append("tokens")

    for name in to_clear:
        target = contextos_dir / name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

    size_after = _dir_size(contextos_dir)
    return {
        "freed_bytes": max(0, size_before - size_after),
        "size_human": _fmt_size(max(0, size_before - size_after)),
        "cleared": to_clear,
    }


def get_disk_usage_bar(used: int, total: int, width: int = 20) -> str:
    """Generate a simple ASCII progress bar for disk usage."""
    if total == 0:
        return "░" * width
    filled = int((used / total) * width)
    return "█" * filled + "░" * (width - filled)
