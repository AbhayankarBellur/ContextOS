"""
ContextOS dashboard.py — Full-screen Textual TUI dashboard.

Live-updating system monitor showing:
  - Projects panel: all indexed projects with doc/chunk counts
  - Recent activity: last searches, context calls, sessions
  - System health: server, index, graph, disk
  - Inline search: type to search without leaving dashboard
  - Keyboard navigation

Usage:
  context dashboard
"""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Optional

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
    from textual.reactive import reactive
    from textual.screen import Screen
    from textual.widgets import (
        DataTable, Footer, Header, Input, Label,
        Placeholder, RichLog, Static, TabbedContent, TabPane,
    )
    from textual.timer import Timer
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Fallback if textual not installed
# ---------------------------------------------------------------------------

def dashboard_not_available():
    from contextos.ui import console, error_panel
    error_panel(
        "Textual Not Installed",
        "context dashboard requires the textual package.",
        "pip install textual"
    )


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _get_system_data(cfg) -> dict:
    """Collect current system state for dashboard panels."""
    data: dict = {
        "server":       False,
        "port":         cfg.port,
        "documents":    0,
        "chunks":       0,
        "last_indexed": "never",
        "model":        "BAAI/bge-small-en-v1.5",
        "graph_nodes":  0,
        "graph_edges":  0,
        "disk_mb":      0.0,
        "projects":     [],
        "sessions":     [],
        "vault_paths":  [],
    }

    # Server check
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        data["server"] = s.connect_ex(("127.0.0.1", cfg.port)) == 0
        s.close()
    except Exception:
        pass

    # Index meta
    meta_file = cfg.metadata_dir / "index_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            data["documents"]    = meta.get("document_count", 0)
            data["chunks"]       = meta.get("chunk_count", 0)
            data["last_indexed"] = meta.get("last_indexed", "never")
            data["model"]        = meta.get("embedding_model", data["model"])
        except Exception:
            pass

    # Graph
    graph_file = cfg.graph_dir / "graph.json"
    if graph_file.exists():
        try:
            gdata = json.loads(graph_file.read_text())
            data["graph_nodes"] = len(gdata.get("nodes", []))
            data["graph_edges"] = len(gdata.get("edges", []))
        except Exception:
            pass

    # Disk
    try:
        from contextos.memory import _dir_size
        total = _dir_size(cfg.contextos_dir)
        data["disk_mb"] = round(total / 1024 / 1024, 1)
    except Exception:
        pass

    # Projects
    try:
        from contextos.memory import get_projects_breakdown
        data["projects"] = get_projects_breakdown(cfg.contextos_dir)
    except Exception:
        pass

    # Sessions
    try:
        from contextos.session import list_sessions
        sessions_dir = cfg.contextos_dir / "sessions"
        data["sessions"] = list_sessions(sessions_dir, limit=5)
    except Exception:
        pass

    data["vault_paths"] = [str(p) for p in cfg.vault_paths]
    return data


# ---------------------------------------------------------------------------
# Textual App
# ---------------------------------------------------------------------------

if TEXTUAL_AVAILABLE:

    DASHBOARD_CSS = """
    Screen {
        background: $background;
    }

    #title-bar {
        height: 3;
        background: $primary-darken-2;
        color: $text;
        content-align: center middle;
        text-style: bold;
        border-bottom: solid $primary;
    }

    #main-container {
        height: 1fr;
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1;
        padding: 0 1;
    }

    .panel {
        border: solid $primary-darken-1;
        padding: 0 1;
        height: 100%;
    }

    .panel-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #health-panel {
        border: solid $success-darken-1;
    }

    #search-bar {
        height: 3;
        padding: 0 1;
        border-top: solid $primary-darken-1;
    }

    #search-input {
        width: 1fr;
    }

    DataTable {
        height: 1fr;
    }

    .metric-good  { color: $success; }
    .metric-warn  { color: $warning; }
    .metric-bad   { color: $error; }
    .metric-muted { color: $text-muted; }
    """

    class ProjectsPanel(Static):
        """Projects table panel."""

        def compose(self) -> ComposeResult:
            yield Label("◈ Projects", classes="panel-title")
            yield DataTable(id="projects-table")

        def on_mount(self):
            table = self.query_one("#projects-table", DataTable)
            table.add_columns("Project", "Docs", "Chunks")

        def update_data(self, projects: list):
            table = self.query_one("#projects-table", DataTable)
            table.clear()
            if not projects:
                table.add_row("—", "—", "—")
                return
            for p in projects[:8]:
                table.add_row(
                    p.get("project",""),
                    str(p.get("documents",0)),
                    str(p.get("chunks",0)),
                )

    class HealthPanel(Static):
        """System health panel."""

        def compose(self) -> ComposeResult:
            yield Label("◎ System Health", classes="panel-title")
            yield Static(id="health-content")

        def update_data(self, data: dict):
            srv    = data["server"]
            docs   = data["documents"]
            nodes  = data["graph_nodes"]
            disk   = data["disk_mb"]
            last   = data["last_indexed"]
            port   = data["port"]

            lines = []
            srv_icon  = "✓" if srv  else "✗"
            srv_color = "metric-good" if srv else "metric-bad"
            lines.append(f"[{srv_color}]{srv_icon} API Server :{port}[/{srv_color}]")
            lines.append(f"◈ Index: {docs:,} docs  {data['chunks']:,} chunks")
            lines.append(f"⬡ Graph: {nodes} nodes  {data['graph_edges']} edges")
            lines.append(f"▣ Disk:  {disk} MB")
            lines.append(f"⟳ Last:  {last[:16] if last != 'never' else 'never'}")

            self.query_one("#health-content", Static).update("\n".join(lines))

    class ActivityPanel(Static):
        """Recent sessions panel."""

        def compose(self) -> ComposeResult:
            yield Label("⟳ Recent Sessions", classes="panel-title")
            yield RichLog(id="activity-log", max_lines=20)

        def update_data(self, sessions: list):
            log = self.query_one("#activity-log", RichLog)
            log.clear()
            if not sessions:
                log.write("[dim]No sessions yet[/dim]")
                return
            for s in sessions[:5]:
                name     = s.get("name","")
                started  = s.get("started_at","")[:16]
                ended    = s.get("ended_at")
                status   = "ended" if ended else "active"
                color    = "dim" if ended else "green"
                events   = len(s.get("events",[]))
                log.write(f"[{color}]● {name}[/{color}] [{started}] {events} events [{status}]")

    class VaultPanel(Static):
        """Vault paths panel."""

        def compose(self) -> ComposeResult:
            yield Label("⬛ Vault Paths", classes="panel-title")
            yield Static(id="vault-content")

        def update_data(self, vault_paths: list):
            if not vault_paths:
                self.query_one("#vault-content", Static).update("[dim]No vaults registered[/dim]")
                return
            lines = []
            for vp in vault_paths[:6]:
                exists = Path(vp).exists()
                icon   = "✓" if exists else "✗"
                color  = "metric-good" if exists else "metric-bad"
                short  = Path(vp).name
                lines.append(f"[{color}]{icon}[/{color}] {short}")
            self.query_one("#vault-content", Static).update("\n".join(lines))

    class SearchResultsScreen(Screen):
        """Overlay screen for inline search results."""

        BINDINGS = [Binding("escape", "dismiss", "Close")]

        def __init__(self, query: str, results: list):
            super().__init__()
            self.query   = query
            self.results = results

        def compose(self) -> ComposeResult:
            yield Static(f"Search: {self.query}", id="search-title")
            table = DataTable(id="results-table")
            yield table
            yield Footer()

        def on_mount(self):
            table = self.query_one("#results-table", DataTable)
            table.add_columns("#", "Title", "Type", "Score")
            for i, r in enumerate(self.results[:15], 1):
                score = max(0.0, 1.0 - float(r.get("_distance", 1)))
                table.add_row(
                    str(i),
                    r.get("title","")[:40],
                    r.get("type",""),
                    f"{score:.2f}",
                )

    class ContextOSDashboard(App):
        """ContextOS live TUI dashboard."""

        TITLE    = "ContextOS Dashboard"
        CSS      = DASHBOARD_CSS
        BINDINGS = [
            Binding("q",   "quit",          "Quit"),
            Binding("r",   "refresh",        "Refresh"),
            Binding("/",   "focus_search",   "Search"),
            Binding("s",   "show_status",    "Status"),
            Binding("ctrl+c", "quit",        "Quit", show=False),
        ]

        _refresh_timer: Optional[Timer] = None

        def __init__(self, cfg):
            super().__init__()
            self.cfg  = cfg
            self._data: dict = {}

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static(
                f"[bold cyan]ContextOS[/bold cyan] [bold blue]v1.2.0[/bold blue]  "
                f"[dim]Local-first knowledge OS · [r] refresh · [/] search · [q] quit[/dim]",
                id="title-bar",
            )
            with Container(id="main-container"):
                yield ProjectsPanel(classes="panel", id="projects-panel")
                yield HealthPanel(classes="panel health-panel", id="health-panel")
                yield ActivityPanel(classes="panel", id="activity-panel")
                yield VaultPanel(classes="panel", id="vault-panel")

            with Horizontal(id="search-bar"):
                yield Input(placeholder="/ to search vault…", id="search-input")

            yield Footer()

        def on_mount(self) -> None:
            self._refresh_data()
            self._refresh_timer = self.set_interval(5, self._refresh_data)

        def _refresh_data(self) -> None:
            self._data = _get_system_data(self.cfg)
            self._update_panels()

        def _update_panels(self) -> None:
            try:
                self.query_one(ProjectsPanel).update_data(self._data.get("projects",[]))
                self.query_one(HealthPanel).update_data(self._data)
                self.query_one(ActivityPanel).update_data(self._data.get("sessions",[]))
                self.query_one(VaultPanel).update_data(self._data.get("vault_paths",[]))
            except Exception:
                pass

        def action_refresh(self) -> None:
            self._refresh_data()
            self.notify("Refreshed", timeout=1)

        def action_focus_search(self) -> None:
            self.query_one("#search-input", Input).focus()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            query = event.value.strip()
            if not query:
                return
            event.input.clear()
            results = self._do_search(query)
            self.push_screen(SearchResultsScreen(query, results))

        def _do_search(self, query: str) -> list:
            try:
                from contextos.embedder import Embedder
                from contextos.store import VectorStore
                embedder = Embedder(self.cfg.embeddings_dir)
                qv       = embedder.embed_query(query)
                store    = VectorStore(self.cfg.lancedb_dir)
                return store.search(query_vector=qv, limit=10)
            except Exception:
                return []


def run_dashboard(cfg) -> None:
    """Entry point called by context dashboard CLI command."""
    if not TEXTUAL_AVAILABLE:
        dashboard_not_available()
        return
    app = ContextOSDashboard(cfg)
    app.run()
