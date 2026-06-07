"""
ContextOS config.py — pydantic-settings Config class.
Reads from .contextos/config.yaml in the current working directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


CONTEXTOS_DIR = ".contextos"
CONFIG_FILE = "config.yaml"

DEFAULT_CONFIG = {
    "project_name": "my-project",
    "vault_paths": [],
    "port": 8080,
    "log_level": "info",
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "version": "1.5.0-rc1",
    "hybrid_search": True,
    "hybrid_alpha": 0.7,
    "embedding_dim": 384,
}


def get_contextos_dir(root: Optional[Path] = None) -> Path:
    """Return the .contextos directory path for the given root (default: cwd)."""
    base = root or Path.cwd()
    return base / CONTEXTOS_DIR


def get_config_path(root: Optional[Path] = None) -> Path:
    return get_contextos_dir(root) / CONFIG_FILE


def load_config(root: Optional[Path] = None) -> "Config":
    """Load config from .contextos/config.yaml, falling back to defaults."""
    config_path = get_config_path(root)
    data = dict(DEFAULT_CONFIG)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            file_data = yaml.safe_load(f) or {}
        data.update(file_data)

    # vault_paths stored as strings, convert to Path list
    vault_paths = [Path(p) for p in data.get("vault_paths", [])]

    return Config(
        project_name=data.get("project_name", "my-project"),
        vault_paths=vault_paths,
        port=int(data.get("port", 8080)),
        log_level=data.get("log_level", "info"),
        embedding_model=data.get("embedding_model", "BAAI/bge-small-en-v1.5"),
        version=data.get("version", "1.4.0-rc1"),
        hybrid_search=bool(data.get("hybrid_search", True)),
        hybrid_alpha=float(data.get("hybrid_alpha", 0.7)),
        embedding_dim=int(data.get("embedding_dim", 384)),
        root=root or Path.cwd(),
    )


def save_config(config: "Config") -> None:
    """Persist config to .contextos/config.yaml."""
    config_path = get_config_path(config.root)
    data = {
        "project_name":   config.project_name,
        "vault_paths":    [str(p) for p in config.vault_paths],
        "port":           config.port,
        "log_level":      config.log_level,
        "embedding_model":config.embedding_model,
        "version":        config.version,
        "hybrid_search":  config.hybrid_search,
        "hybrid_alpha":   config.hybrid_alpha,
        "embedding_dim":  config.embedding_dim,
    }
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)


class Config:
    """ContextOS runtime configuration."""

    def __init__(
        self,
        project_name: str = "my-project",
        vault_paths: Optional[list[Path]] = None,
        port: int = 8080,
        log_level: str = "info",
        embedding_model: str = "BAAI/bge-small-en-v1.5",
        version: str = "1.4.0-rc1",
        hybrid_search: bool = True,
        hybrid_alpha: float = 0.7,
        embedding_dim: int = 384,
        root: Optional[Path] = None,
    ):
        self.project_name = project_name
        self.vault_paths: list[Path] = vault_paths or []
        self.port = port
        self.log_level = log_level
        self.embedding_model = embedding_model
        self.version = version
        self.hybrid_search = hybrid_search
        self.hybrid_alpha = hybrid_alpha
        self.embedding_dim = embedding_dim
        self.root = root or Path.cwd()

    @property
    def contextos_dir(self) -> Path:
        return self.root / CONTEXTOS_DIR

    @property
    def embeddings_dir(self) -> Path:
        return self.contextos_dir / "embeddings"

    @property
    def lancedb_dir(self) -> Path:
        return self.contextos_dir / "lancedb"

    @property
    def graph_dir(self) -> Path:
        return self.contextos_dir / "graph"

    @property
    def tokens_dir(self) -> Path:
        return self.contextos_dir / "tokens"

    @property
    def cache_dir(self) -> Path:
        return self.contextos_dir / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.contextos_dir / "logs"

    @property
    def metadata_dir(self) -> Path:
        return self.contextos_dir / "metadata"
