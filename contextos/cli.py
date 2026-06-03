"""
ContextOS cli.py — Premium CLI experience.
Spec: panels, live updates, progress bars, rich tables, structured output.
Never plain print(). Never raw JSON. Never argparse-style output.
"""
from __future__ import annotations
import json, time
from pathlib import Path
from typing import Optional
import typer
from rich.columns import Columns
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich import box
import logging

from contextos.ui import (
    console, brand_rule, print_logo, ok, warn, err, info,
    next_action, score_style, type_style, error_panel, empty_state,
    ICONS, VERSION
)

app = typer.Typer(name="context", add_completion=False, rich_markup_mode="rich", no_args_is_help=False)
token_app  = typer.Typer(help="Manage API tokens")
memory_app = typer.Typer(help="Memory and disk management")
cache_app  = typer.Typer(help="File read cache")
app.add_typer(token_app,  name="token")
app.add_typer(memory_app, name="memory")
app.add_typer(cache_app,  name="cache")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


# ── helpers ─────────────────────────────────────────────────────────────────

def _root() -> Path:
    return Path.cwd()

def _cfg():
    from contextos.config import load_config, get_contextos_dir
    root = _root()
    if not get_contextos_dir(root).exists():
        error_panel("Not Initialized",
            "No .contextos/ directory found in this folder.",
            "Run: context init")
        raise typer.Exit(1)
    return load_config(root)

def _fmt_size(b: int) -> str:
    for u in ("B","KB","MB","GB"):
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"


# ── callback (no args = welcome screen) ─────────────────────────────────────

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """ContextOS — Local-first knowledge OS for AI coding agents."""
    if ctx.invoked_subcommand is None:
        print_logo()
        console.print(Panel(
            "[dim]A 100% local, filesystem-native knowledge vault for AI coding agents.\n"
            "Persistent project memory via a localhost API. Zero cloud. Fully offline.[/dim]\n\n"
            f"  [bold cyan]context init[/bold cyan]               Initialize in current directory\n"
            f"  [bold cyan]context import <path>[/bold cyan]      Register a Markdown vault\n"
            f"  [bold cyan]context index[/bold cyan]              Build vector index\n"
            f"  [bold cyan]context serve[/bold cyan]              Start API on 127.0.0.1:8080\n"
            f"  [bold cyan]context search \"<query>\"[/bold cyan]  Semantic search\n"
            f"  [bold cyan]context doctor[/bold cyan]             Validate setup\n\n"
            f"  [dim]context --help for all commands[/dim]",
            title=f"[bold cyan]ContextOS[/bold cyan] [bold blue]v{VERSION}[/bold blue]",
            border_style="cyan", padding=(0, 2)
        ))


# ── init ────────────────────────────────────────────────────────────────────

@app.command("init")
def cmd_init():
    """Initialize ContextOS in the current directory."""
    from contextos.config import get_contextos_dir, save_config, Config
    brand_rule("init")
    root = _root()
    cfg = Config(root=root)
    already = get_contextos_dir(root).exists()
    created = []
    for d in [cfg.contextos_dir, cfg.embeddings_dir, cfg.lancedb_dir,
              cfg.graph_dir, cfg.tokens_dir, cfg.cache_dir, cfg.logs_dir, cfg.metadata_dir]:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(d.name)
        else:
            d.mkdir(parents=True, exist_ok=True)
    save_config(cfg)
    gi = root / ".gitignore"
    if gi.exists():
        if ".contextos/" not in gi.read_text():
            gi.open("a").write("\n.contextos/\n")
    else:
        gi.write_text(".contextos/\n")

    status = "Re-initialized" if already else "Initialized"
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    table.add_column("k", style="dim", width=18); table.add_column("v", style="bold")
    table.add_row("Location", str(cfg.contextos_dir))
    table.add_row("Directories", ", ".join(created) if created else "already exist")
    table.add_row(".gitignore", "updated")

    console.print(Panel(table,
        title=f"[success]{ICONS['success']} {status}[/success]",
        border_style="green", padding=(0, 1)))
    next_action("context import <vault-path>", "Register your Markdown vault")


# ── import ───────────────────────────────────────────────────────────────────

@app.command("import")
def cmd_import(path: str = typer.Argument(..., help="Path to Markdown vault directory")):
    """Register a vault and scan all Markdown documents."""
    from contextos.config import save_config
    from contextos.vault import scan_vault, write_registry
    brand_rule("import")
    cfg = _cfg()
    vp = Path(path).resolve()
    if not vp.exists(): error_panel("Path Not Found", str(vp), f"Expected: {vp}"); raise typer.Exit(1)
    if not vp.is_dir(): error_panel("Not a Directory", str(vp)); raise typer.Exit(1)

    with console.status(f"[cyan]{ICONS['spin']} Scanning {vp.name}…[/cyan]"):
        docs = scan_vault(vp)

    if not docs:
        empty_state("No Markdown files found in vault.", f"context import ./my-project"); raise typer.Exit(0)

    registry_path = write_registry(docs, cfg.metadata_dir)
    if vp not in cfg.vault_paths: cfg.vault_paths.append(vp); save_config(cfg)

    # Build type breakdown
    tc: dict[str, int] = {}
    for d in docs: tc[d.type.value] = tc.get(d.type.value, 0) + 1

    table = Table(show_header=True, box=box.SIMPLE_HEAD, padding=(0, 1))
    table.add_column("Type", style="cyan", min_width=16)
    table.add_column("Count", justify="right", style="bold green")
    for t, c in sorted(tc.items()): table.add_row(t, str(c))
    table.add_section(); table.add_row("[bold]Total[/bold]", f"[bold]{len(docs)}[/bold]")

    console.print(Panel(table,
        title=f"[success]{ICONS['success']} Vault Registered — {vp.name}[/success]",
        border_style="green", padding=(0, 1)))
    next_action("context index", "Build the search index")


# ── index ─────────────────────────────────────────────────────────────────────

@app.command("index")
def cmd_index():
    """Build vector index, embeddings, and knowledge graph."""
    from contextos.vault import load_registry, get_content_hash
    from contextos.chunker import chunk_all_documents
    from contextos.embedder import Embedder
    from contextos.store import VectorStore
    from contextos.graph import GraphBuilder
    from contextos.schema import Document, DocumentType, DocumentStatus
    from datetime import date
    brand_rule("index")
    cfg = _cfg()
    registry = load_registry(cfg.metadata_dir)
    if not registry:
        empty_state("No documents registered.", "context import <path>"); raise typer.Exit(0)

    # Load documents
    documents: list[Document] = []
    for rec in registry:
        fp = Path(rec["filepath"])
        if not fp.exists(): warn(f"Missing: {fp.name}"); continue
        documents.append(Document(
            id=rec["id"], project=rec["project"], type=DocumentType(rec["type"]),
            domain=rec.get("domain"), status=DocumentStatus(rec.get("status","draft")),
            owner=rec.get("owner"),
            updated_at=date.fromisoformat(rec["updated_at"]) if rec.get("updated_at") else None,
            tags=rec.get("tags",[]), title=rec["title"], filepath=fp,
            content=fp.read_text(encoding="utf-8")))

    doc_map = {d.id: d for d in documents}
    stats = {"docs": len(documents), "chunks": 0, "nodes": 0, "edges": 0}
    t_total = time.time()

    # Live updating panel
    def make_live_table(step: str, elapsed: float) -> Panel:
        t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
        t.add_column("k", style="dim", width=20); t.add_column("v", style="bold cyan")
        t.add_row("Step", step)
        t.add_row("Documents", str(stats["docs"]))
        t.add_row("Chunks", str(stats["chunks"]) if stats["chunks"] else "—")
        t.add_row("Graph Nodes", str(stats["nodes"]) if stats["nodes"] else "—")
        t.add_row("Graph Edges", str(stats["edges"]) if stats["edges"] else "—")
        t.add_row("Elapsed", f"{elapsed:.1f}s")
        return Panel(t, title=f"[cyan]{ICONS['spin']} Indexing Project[/cyan]", border_style="cyan", padding=(0,1))

    with Live(make_live_table("Chunking…", 0), console=console, refresh_per_second=4) as live:
        # Step 1: Chunk
        chunks_by_doc = chunk_all_documents(documents, cfg.cache_dir)
        stats["chunks"] = sum(len(v) for v in chunks_by_doc.values())
        live.update(make_live_table("Generating embeddings…", time.time()-t_total))

        # Step 2: Embed with progress bar
        embedder = Embedder(cfg.embeddings_dir)
        all_chunks = [c for cl in chunks_by_doc.values() for c in cl]
        texts = [c.content for c in all_chunks]
        BATCH = 32
        with Progress(
            SpinnerColumn(), TextColumn("[cyan]Embedding[/cyan]"),
            BarColumn(bar_width=30), TaskProgressColumn(),
            TimeElapsedColumn(), console=console, transient=True
        ) as prog:
            task = prog.add_task("embed", total=len(texts))
            for i in range(0, len(texts), BATCH):
                batch_t = texts[i:i+BATCH]; batch_c = all_chunks[i:i+BATCH]
                vecs = embedder.embed(batch_t)
                for c, v in zip(batch_c, vecs): c.embedding = v
                prog.advance(task, len(batch_c))
                live.update(make_live_table("Generating embeddings…", time.time()-t_total))

        # Step 3: LanceDB
        live.update(make_live_table("Writing to LanceDB…", time.time()-t_total))
        store = VectorStore(cfg.lancedb_dir)
        written = store.upsert_chunks(all_chunks, doc_map)
        stats["chunks"] = written

        # Step 4: Graph
        live.update(make_live_table("Building knowledge graph…", time.time()-t_total))
        gb = GraphBuilder(); gb.build(documents); gb.save(cfg.graph_dir)
        s = gb.get_summary(); stats["nodes"] = s["nodes"]; stats["edges"] = s["edges"]
        live.update(make_live_table("Complete", time.time()-t_total))

    elapsed = time.time()-t_total
    cfg.metadata_dir.mkdir(exist_ok=True)
    meta = cfg.metadata_dir/"index_meta.json"
    meta.write_text(json.dumps({"last_indexed":time.strftime("%Y-%m-%dT%H:%M:%S"),
        "document_count":len(documents),"chunk_count":written,"embedding_model":cfg.embedding_model},indent=2))

    result_table = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    result_table.add_column("k", style="dim", width=20); result_table.add_column("v", style="bold")
    result_table.add_row("Project", cfg.project_name)
    result_table.add_row("Documents Indexed", f"[cyan]{len(documents)}[/cyan]")
    result_table.add_row("Chunks Generated", f"[cyan]{written:,}[/cyan]")
    result_table.add_row("Graph Nodes", f"[cyan]{stats['nodes']}[/cyan]")
    result_table.add_row("Graph Edges", f"[cyan]{stats['edges']}[/cyan]")
    result_table.add_row("Time", f"[green]{elapsed:.1f}s[/green]")
    result_table.add_row("Model", f"[dim]{cfg.embedding_model}[/dim]")

    console.print(Panel(result_table,
        title=f"[success]{ICONS['success']} Project Indexed[/success]",
        border_style="green", padding=(0,1)))
    next_action("context serve", "Start the retrieval server")


# ── search ────────────────────────────────────────────────────────────────────

@app.command("search")
def cmd_search(
    query: str = typer.Argument(...),
    project: Optional[str] = typer.Option(None, "-p","--project"),
    doc_type: Optional[str] = typer.Option(None, "-t","--type"),
    domain: Optional[str] = typer.Option(None, "-d","--domain"),
    limit: int = typer.Option(5, "-n","--limit"),
):
    """Semantic search across the indexed vault."""
    from contextos.embedder import Embedder
    from contextos.store import VectorStore
    brand_rule("search")
    cfg = _cfg()
    with console.status(f"[cyan]{ICONS['spin']} Searching…[/cyan]"):
        emb = Embedder(cfg.embeddings_dir)
        qv  = emb.embed_query(query)
        st  = VectorStore(cfg.lancedb_dir)
        raw = st.search(query_vector=qv, project=project, type_filter=doc_type, domain_filter=domain, limit=max(1,min(20,limit)))

    if not raw:
        empty_state(f'No results for "{query}"', "context index"); raise typer.Exit(0)

    # Results table
    table = Table(title=f"[bold]Top Results[/bold]  [dim]{query}[/dim]",
                  box=box.ROUNDED, border_style="cyan", show_lines=False)
    table.add_column("#", width=3, style="dim")
    table.add_column("Title", style="bold", min_width=28)
    table.add_column("Type", style="cyan", width=14)
    table.add_column("Domain", width=12)
    table.add_column("Score", justify="right", width=7)

    for i, r in enumerate(raw, 1):
        score  = max(0.0, 1.0 - float(r.get("_distance", 0)))
        sc     = f"[{score_style(score)}]{score:.2f}[/{score_style(score)}]"
        dt     = r.get("type","")
        domain_val = r.get("domain","") or "—"
        table.add_row(str(i), r.get("title",""), f"[{type_style(dt)}]{dt}[/{type_style(dt)}]", domain_val, sc)

    console.print(table)

    # Expand best result in a panel
    best = raw[0]
    snippet = best.get("content","")[:400].replace("\n"," ")
    if len(best.get("content","")) > 400: snippet += "…"
    best_score = max(0.0, 1.0 - float(best.get("_distance",0)))
    console.print(Panel(
        f"[dim]{best.get('heading','')}[/dim]\n\n{snippet}\n\n[dim]{best.get('filepath','')}[/dim]",
        title=f"[bold]1. {best.get('title','')}[/bold]  [{score_style(best_score)}]{best_score:.2f}[/{score_style(best_score)}]",
        border_style="cyan", padding=(0,2)))


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command("serve")
def cmd_serve(port: int = typer.Option(8080, "--port")):
    """Start the ContextOS API server on 127.0.0.1."""
    brand_rule("serve")
    cfg = _cfg()

    # Startup checklist panel
    checks = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    checks.add_column("ic", width=3); checks.add_column("item")

    def chk(label: str, ok_flag: bool):
        icon = f"[success]{ICONS['success']}[/success]" if ok_flag else f"[warning]{ICONS['warning']}[/warning]"
        checks.add_row(icon, label)

    meta = cfg.metadata_dir/"index_meta.json"
    indexed = json.loads(meta.read_text()).get("document_count",0) if meta.exists() else 0
    chk(f"Index loaded  ({indexed} documents)", indexed > 0)
    chk(f"Embeddings cached  ({cfg.embeddings_dir.name})", cfg.embeddings_dir.exists())
    chk("Graph engine ready", (cfg.graph_dir/"graph.json").exists())
    chk(f"LanceDB connected  (.contextos/lancedb)", cfg.lancedb_dir.exists())

    checks.add_section()
    checks.add_row(f"[success]{ICONS['server']}[/success]",
        f"[bold]Server Running  [cyan]http://127.0.0.1:{port}[/cyan][/bold]")
    checks.add_row("", f"[dim]Docs: http://127.0.0.1:{port}/docs[/dim]")
    checks.add_row("", f"[dim]Health: http://127.0.0.1:{port}/health[/dim]")
    checks.add_section()
    checks.add_row("[dim]⌨[/dim]", "[dim]Press Ctrl+C to stop[/dim]")

    console.print(Panel(checks, title="[bold]ContextOS Local Server[/bold]",
                        border_style="green", padding=(0,2)))

    from contextos.api import run_server
    run_server(port=port)


# ── status ────────────────────────────────────────────────────────────────────

@app.command("status")
def cmd_status():
    """Show index health, server status, and vault info."""
    import socket
    from contextos.config import load_config, get_contextos_dir
    brand_rule("status")
    root = _root()
    if not get_contextos_dir(root).exists():
        error_panel("Not Initialized","Run context init first."); raise typer.Exit(1)
    cfg = load_config(root)

    meta = cfg.metadata_dir/"index_meta.json"
    im = json.loads(meta.read_text()) if meta.exists() else {}

    srv = False
    try:
        s=socket.socket(); s.settimeout(0.5); srv=s.connect_ex(("127.0.0.1",cfg.port))==0; s.close()
    except: pass

    t = Table(show_header=False, box=box.ROUNDED, border_style="cyan", min_width=52, padding=(0,1))
    t.add_column("k", style="dim", width=22); t.add_column("v", style="bold")
    t.add_row("Root", str(root))
    t.add_row("Registered vaults", str(len(cfg.vault_paths)))
    t.add_row("Documents indexed", str(im.get("document_count","—")))
    t.add_row("Chunks indexed", f"{im.get('chunk_count',0):,}" if im.get("chunk_count") else "—")
    t.add_row("Last indexed", im.get("last_indexed","—"))
    t.add_row("Embedding model", im.get("embedding_model", cfg.embedding_model))
    srv_str = f"[success]{ICONS['success']} running :{cfg.port}[/success]" if srv else f"[error]{ICONS['error']} not running[/error]"
    t.add_row("API server", srv_str)
    t.add_row("Version", f"v{VERSION}")

    console.print(Panel(t, title="[bold]ContextOS Status[/bold]", border_style="cyan"))
    if cfg.vault_paths:
        console.print("\n[bold]Registered vaults:[/bold]")
        for vp in cfg.vault_paths:
            ok_flag = Path(vp).exists()
            ic = f"[success]{ICONS['success']}[/success]" if ok_flag else f"[error]{ICONS['error']}[/error]"
            console.print(f"  {ic} {vp}")


# ── graph ─────────────────────────────────────────────────────────────────────

@app.command("graph")
def cmd_graph(fmt: str = typer.Option("text","--format")):
    """Show knowledge graph: nodes, edges, relationships."""
    from contextos.graph import GraphBuilder
    brand_rule("graph")
    cfg = _cfg()
    gp = cfg.graph_dir/"graph.json"
    if not gp.exists():
        empty_state("No graph built yet.","context index"); raise typer.Exit(0)
    gb = GraphBuilder(); gb.load(cfg.graph_dir)
    s = gb.get_summary()

    if fmt == "json":
        console.print_json(gp.read_text()); return

    # Rich Tree for relationships
    data = json.loads(gp.read_text())
    node_map = {n["id"]: n for n in data.get("nodes",[])}
    domain_tree: dict[str, list] = {}
    for n in data.get("nodes",[]):
        d = n.get("domain") or "general"
        domain_tree.setdefault(d, []).append(n)

    tree = Tree(f"[bold cyan]{ICONS['graph']} Knowledge Graph[/bold cyan]")
    for domain, nodes in sorted(domain_tree.items()):
        branch = tree.add(f"[bold]{domain}[/bold]")
        for n in nodes[:8]:
            dt = n.get("type","")
            branch.add(f"[{type_style(dt)}]{n.get('title',n['id'][:12])}[/{type_style(dt)}]  [dim]{dt}[/dim]")
        if len(nodes) > 8: branch.add(f"[dim]…and {len(nodes)-8} more[/dim]")

    stats_table = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    stats_table.add_column("k", style="dim", width=18); stats_table.add_column("v", style="bold cyan")
    stats_table.add_row("Total nodes", str(s["nodes"]))
    stats_table.add_row("Total edges", str(s["edges"]))
    for t, c in sorted(s.get("types",{}).items(), key=lambda x:-x[1]):
        bar = "█"*min(c*2,20)+"░"*(20-min(c*2,20))
        stats_table.add_row(f"  {t}", f"[dim]{bar}[/dim] {c}")

    console.print(Panel(stats_table, title="[bold]Graph Summary[/bold]", border_style="cyan", padding=(0,1)))
    console.print(); console.print(tree)


# ── token commands ─────────────────────────────────────────────────────────────

@token_app.command("create")
def token_create(name: str = typer.Argument(..., help="Label for this token")):
    """Generate a new API token. Raw value shown ONCE — save immediately."""
    from contextos.auth import generate_token
    brand_rule("token create")
    cfg = _cfg()
    raw, token = generate_token(name, cfg.tokens_dir)

    t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    t.add_column("k", style="dim", width=10); t.add_column("v", style="bold")
    t.add_row("ID",      token.id)
    t.add_row("Name",    token.name)
    t.add_row("Created", token.created_at.strftime("%Y-%m-%d %H:%M UTC"))
    t.add_section()
    t.add_row("Token", f"[bold cyan]{raw}[/bold cyan]")
    t.add_row("",      "[dim]Copy now — never shown again[/dim]")

    console.print(Panel(t, title=f"[success]{ICONS['success']} Token Created[/success]",
                        border_style="green", padding=(0,2)))
    console.print()
    console.print(f"  [dim]Add to shell profile:[/dim]  [bold]export CONTEXTOS_TOKEN={raw}[/bold]")


@token_app.command("revoke")
def token_revoke(token_id: str = typer.Argument(...)):
    """Revoke an API token immediately."""
    from contextos.auth import revoke_token
    cfg = _cfg()
    if revoke_token(token_id, cfg.tokens_dir):
        ok(f"Token [bold]{token_id}[/bold] revoked — next request returns 401")
    else:
        error_panel("Token Not Found", token_id, "Run: context token list")
        raise typer.Exit(1)


@token_app.command("list")
def token_list():
    """List all tokens. Raw values are never displayed."""
    from contextos.auth import list_tokens
    brand_rule("token list")
    cfg = _cfg()
    tokens = list_tokens(cfg.tokens_dir)
    if not tokens:
        empty_state("No tokens found.", "context token create <name>"); raise typer.Exit(0)

    t = Table(title="[bold]API Tokens[/bold]", box=box.ROUNDED, border_style="cyan")
    t.add_column("ID", style="cyan", no_wrap=True)
    t.add_column("Name", style="bold")
    t.add_column("Created", style="dim")
    t.add_column("Last Used", style="dim")
    t.add_column("Status", width=10)
    for tk in tokens:
        lu = tk.last_used.strftime("%Y-%m-%d %H:%M") if tk.last_used else "—"
        st = f"[error]REVOKED[/error]" if tk.revoked else f"[success]active[/success]"
        t.add_row(tk.id, tk.name, tk.created_at.strftime("%Y-%m-%d %H:%M"), lu, st)

    console.print(); console.print(t)
    console.print(f"\n[dim]Raw token values are never stored or displayed.[/dim]")


# ── memory commands ────────────────────────────────────────────────────────────

@memory_app.command("status")
def memory_status():
    """Show disk usage breakdown for .contextos/ components."""
    from contextos.memory import get_disk_breakdown, get_disk_usage_bar
    brand_rule("memory status")
    cfg = _cfg()
    bd = get_disk_breakdown(cfg.contextos_dir)
    total = bd.pop("_total")

    t = Table(title="[bold]Disk Usage — .contextos/[/bold]", box=box.ROUNDED, border_style="cyan")
    t.add_column("Component", style="cyan", min_width=14)
    t.add_column("Size", justify="right", style="bold", width=10)
    t.add_column("Usage", min_width=24)

    total_bytes = total["size_bytes"]
    for name, info_d in sorted(bd.items(), key=lambda x: -x[1]["size_bytes"]):
        sb = info_d["size_bytes"]
        pct = (sb/total_bytes*100) if total_bytes else 0
        bar = "[cyan]" + "█"*int(pct/5) + "[/cyan][dim]" + "░"*(20-int(pct/5)) + "[/dim]"
        t.add_row(name, info_d["size_human"], f"{bar} [dim]{pct:.0f}%[/dim]")

    t.add_section()
    t.add_row("[bold]Total[/bold]", f"[bold]{total['size_human']}[/bold]", "")
    console.print(Panel(t, border_style="cyan", padding=(0,1)))


@memory_app.command("projects")
def memory_projects():
    """List all indexed projects with document counts."""
    from contextos.memory import get_projects_breakdown
    brand_rule("memory projects")
    cfg = _cfg()
    projects = get_projects_breakdown(cfg.contextos_dir)
    if not projects:
        empty_state("No projects indexed.", "context import <path>\ncontext index"); raise typer.Exit(0)

    t = Table(title="[bold]Indexed Projects[/bold]", box=box.ROUNDED, border_style="cyan")
    t.add_column("Project", style="bold cyan")
    t.add_column("Documents", justify="right", style="green")
    t.add_column("Chunks", justify="right", style="dim")
    for p in projects:
        t.add_row(p["project"], str(p["documents"]), str(p.get("chunks",0)))
    console.print(); console.print(t)


@memory_app.command("purge")
def memory_purge(
    project: str = typer.Argument(..., help="Project name to purge from index"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove a project's index data. Vault files are NOT touched."""
    from contextos.memory import purge_project
    brand_rule("memory purge")
    cfg = _cfg()
    if not confirm:
        warn(f"This will delete all indexed data for project [bold]{project}[/bold].")
        warn("Vault files are NOT affected. Re-run context index to restore.")
        typer.confirm("Proceed?", abort=True)
    with console.status(f"[cyan]{ICONS['spin']} Purging {project}…[/cyan]"):
        result = purge_project(project, cfg.contextos_dir)
    console.print(Panel(
        f"  [dim]Chunks removed:[/dim]  [bold]{result['deleted_chunks']}[/bold]\n"
        f"  [dim]Space freed:[/dim]     [bold]{_fmt_size(result['freed_bytes'])}[/bold]",
        title=f"[success]{ICONS['success']} Project Purged — {project}[/success]",
        border_style="green", padding=(0,2)))
    next_action(f"context index", "Re-index to restore project")


@memory_app.command("archive")
def memory_archive(
    project: str = typer.Argument(..., help="Project to archive"),
    confirm: bool = typer.Option(False, "--yes", "-y"),
):
    """Archive a project's index to a compressed tarball, then purge live index."""
    from contextos.memory import archive_project
    brand_rule("memory archive")
    cfg = _cfg()
    if not confirm:
        warn(f"Project [bold]{project}[/bold] will be archived and removed from live index.")
        typer.confirm("Proceed?", abort=True)
    with console.status(f"[cyan]{ICONS['spin']} Archiving {project}…[/cyan]"):
        archive_path = archive_project(project, cfg.contextos_dir)
    console.print(Panel(
        f"  [dim]Archive:[/dim]  [bold cyan]{archive_path}[/bold cyan]\n"
        f"  [dim]Live index cleared. Restore with: context index[/dim]",
        title=f"[success]{ICONS['success']} Project Archived — {project}[/success]",
        border_style="green", padding=(0,2)))


@memory_app.command("clear-embeddings")
def memory_clear_embeddings(confirm: bool = typer.Option(False,"--yes","-y")):
    """Delete cached embedding model (~130MB). Re-downloaded on next index."""
    from contextos.memory import clear_embeddings_cache
    cfg = _cfg()
    if not confirm:
        warn("This deletes the cached embedding model. Next context index will re-download ~130MB.")
        typer.confirm("Proceed?", abort=True)
    result = clear_embeddings_cache(cfg.contextos_dir)
    ok(f"Embedding cache cleared. Freed [bold]{result['size_human']}[/bold].")


@memory_app.command("reset")
def memory_reset(
    keep_tokens: bool = typer.Option(True, "--keep-tokens/--wipe-tokens"),
    confirm: bool = typer.Option(False, "--yes", "-y"),
):
    """Full reset of .contextos/ index. Vault files are NOT touched."""
    from contextos.memory import reset_index
    brand_rule("memory reset")
    cfg = _cfg()
    if not confirm:
        warn("[bold red]Full reset will wipe ALL index data: LanceDB, graph, cache, embeddings, metadata.[/bold red]")
        warn("Vault documents are NOT touched. Everything can be rebuilt with context index.")
        typer.confirm("Proceed?", abort=True)
    with console.status(f"[cyan]{ICONS['spin']} Resetting index…[/cyan]"):
        result = reset_index(cfg.contextos_dir, keep_tokens=keep_tokens)
    console.print(Panel(
        f"  [dim]Freed:[/dim]    [bold]{_fmt_size(result['freed_bytes'])}[/bold]\n"
        f"  [dim]Cleared:[/dim]  {', '.join(result['cleared'])}",
        title=f"[success]{ICONS['success']} Index Reset[/success]",
        border_style="green", padding=(0,2)))
    next_action("context import <path>  &&  context index", "Rebuild the index")


# ── grep ──────────────────────────────────────────────────────────────────────

@app.command("grep")
def cmd_grep(
    pattern: str = typer.Argument(...),
    path: str = typer.Option(".", "--path"),
    file_type: Optional[str] = typer.Option(None, "--type", "-t"),
    context_lines: int = typer.Option(2, "--context", "-C"),
    literal: bool = typer.Option(False, "--literal", "-F"),
    limit: int = typer.Option(50, "--limit"),
    fmt: str = typer.Option("text", "--format"),
):
    """Fast regex/literal search across codebase files."""
    import subprocess, re as re_mod
    brand_rule("grep")
    sp = Path(path).resolve()
    if not sp.exists(): error_panel("Path Not Found", str(sp)); raise typer.Exit(1)

    matches = []
    t0 = time.time()
    rg_ok = False
    try:
        subprocess.run(["rg","--version"], capture_output=True, check=True); rg_ok = True
    except (FileNotFoundError, subprocess.CalledProcessError): pass

    with console.status(f"[cyan]{ICONS['spin']} Searching with {'ripgrep' if rg_ok else 'python'}…[/cyan]"):
        if rg_ok:
            cmd = ["rg","--json",f"--context={context_lines}",f"--max-count={limit}"]
            if literal: cmd.append("--fixed-strings")
            if file_type: cmd += [f"--type={file_type}"]
            cmd += [pattern, str(sp)]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                for line in r.stdout.splitlines():
                    try:
                        obj = json.loads(line)
                        if obj.get("type") == "match":
                            m = obj["data"]
                            matches.append({"file":m["path"]["text"],"line":m["line_number"],"content":m["lines"]["text"].rstrip()})
                    except: pass
            except: rg_ok = False

        if not rg_ok:
            flags = 0 if literal else re_mod.IGNORECASE
            ext = f".{file_type}" if file_type else None
            for f in sp.rglob("*"):
                if ext and f.suffix != ext: continue
                if any(p.startswith(".") for p in f.parts): continue
                if not f.is_file(): continue
                try:
                    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for i, line in enumerate(lines):
                        if (pattern in line) if literal else bool(re_mod.search(pattern, line, flags)):
                            matches.append({"file":str(f),"line":i+1,"content":line.rstrip()})
                            if len(matches)>=limit: break
                except: pass
                if len(matches)>=limit: break

    latency_ms = int((time.time()-t0)*1000)

    if fmt == "json":
        console.print_json(json.dumps({"matches":matches,"total":len(matches),"latency_ms":latency_ms})); return

    if not matches:
        empty_state(f'No matches for "{pattern}"', f'context grep "{pattern}" --path <dir>'); return

    t = Table(title=f"[bold]Matches[/bold]  [dim]{pattern}[/dim]  [dim]{len(matches)} results · {latency_ms}ms · {'rg' if rg_ok else 'py'}[/dim]",
              box=box.SIMPLE_HEAD, border_style="cyan", show_lines=False)
    t.add_column("File", style="cyan", min_width=30)
    t.add_column("Line", justify="right", style="dim", width=6)
    t.add_column("Match")

    cur_file = None
    for m in matches:
        short = "/".join(Path(m["file"]).parts[-3:])
        line_content = m["content"][:100]
        if m["file"] != cur_file:
            cur_file = m["file"]
            t.add_row(f"[bold]{short}[/bold]", str(m["line"]), line_content)
        else:
            t.add_row("", str(m["line"]), line_content)

    console.print(t)


# ── read ──────────────────────────────────────────────────────────────────────

@app.command("read")
def cmd_read(
    filepath: str = typer.Argument(...),
    lines: Optional[str] = typer.Option(None, "--lines"),
    fmt: str = typer.Option("raw", "--format"),
):
    """Read a file with optional line-range slicing."""
    import hashlib
    fp = Path(filepath).resolve()
    if not fp.exists(): error_panel("File Not Found", str(fp)); raise typer.Exit(1)

    content = fp.read_text(encoding="utf-8", errors="ignore")
    all_lines = content.splitlines(); total = len(all_lines)
    start, end = 0, total
    if lines:
        parts = lines.split(":")
        try:
            if parts[0]: start = int(parts[0])-1
            if len(parts)>1 and parts[1]: end = int(parts[1])
        except ValueError: warn("Invalid --lines format. Use start:end e.g. 10:50")

    sliced = "\n".join(all_lines[start:end])
    chash = hashlib.sha256(content.encode()).hexdigest()

    if fmt == "meta":
        ext = fp.suffix.lstrip(".")
        lm = {"py":"python","ts":"typescript","js":"javascript","md":"markdown","rs":"rust","go":"go"}
        t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
        t.add_column("k",style="dim",width=14); t.add_column("v",style="bold")
        t.add_row("File",str(fp)); t.add_row("Lines",f"{start+1}–{min(end,total)} / {total}")
        t.add_row("Size",f"{fp.stat().st_size:,} bytes"); t.add_row("Language",lm.get(ext,ext or "unknown"))
        t.add_row("Hash",chash[:16]+"…")
        console.print(t); console.print()

    console.print(Panel(sliced, title=f"[bold]{fp.name}[/bold]  [dim]:{start+1}–{min(end,total)}[/dim]",
                        border_style="cyan", padding=(0,2)))


# ── tree ──────────────────────────────────────────────────────────────────────

@app.command("tree")
def cmd_tree(
    path: str = typer.Option(".", "--path"),
    depth: int = typer.Option(3, "--depth"),
    fmt: str = typer.Option("text", "--format"),
):
    """Show project directory tree with file stats."""
    brand_rule("tree")
    root = Path(path).resolve()
    if not root.exists(): error_panel("Path Not Found", str(root)); raise typer.Exit(1)

    SKIP = {".git","__pycache__",".contextos","node_modules",".venv","venv","dist","build"}

    def build(d: Path, cur: int) -> dict:
        r = {}
        try: items = sorted(d.iterdir(), key=lambda x:(x.is_file(),x.name.lower()))
        except: return r
        for item in items:
            if item.name in SKIP or item.name.startswith("."): continue
            if item.is_dir() and cur < depth: r[item.name+"/"] = build(item, cur+1)
            elif item.is_file(): r[item.name] = item.stat().st_size
        return r

    td = build(root, 1)
    if fmt == "json": console.print_json(json.dumps({"root":root.name,"tree":td})); return

    total_files = sum(1 for f in root.rglob("*") if f.is_file() and not any(p in SKIP or p.startswith(".") for p in f.parts))
    lc: dict[str,int] = {}
    for f in root.rglob("*"):
        if f.is_file() and not any(p in SKIP or p.startswith(".") for p in f.parts):
            ext = f.suffix.lstrip(".") or "other"; lc[ext] = lc.get(ext,0)+1

    rich_tree = Tree(f"[bold cyan]{root.name}[/bold cyan]")
    def add(node, data: dict):
        for name, val in data.items():
            if isinstance(val, dict): add(node.add(f"[bold cyan]{name}[/bold cyan]"), val)
            else: node.add(f"[white]{name}[/white]  [dim]{_fmt_size(val)}[/dim]" if isinstance(val,int) else f"[white]{name}[/white]")
    add(rich_tree, td)
    console.print(); console.print(rich_tree)
    top = sorted(lc.items(), key=lambda x:-x[1])[:5]
    console.print(f"\n  [dim]{total_files} files  ·  {', '.join(f'{c} .{e}' for e,c in top)}[/dim]")


# ── changelog ────────────────────────────────────────────────────────────────

@app.command("changelog")
def cmd_changelog(days: int = typer.Option(30,"--days"), fmt: str = typer.Option("text","--format")):
    """Show recent git commit history."""
    import subprocess
    brand_rule("changelog")
    try:
        r = subprocess.run(["git","log",f"--since={days} days ago","--pretty=format:%h|%ae|%ad|%s","--date=short","--name-only"],
            capture_output=True, text=True, cwd=str(_root()), timeout=10)
        if r.returncode != 0: warn("Not a git repository."); raise typer.Exit(0)
    except (FileNotFoundError, Exception): warn("git not available."); raise typer.Exit(0)

    commits, cur = [], None
    for line in r.stdout.splitlines():
        if "|" in line and line.count("|")>=3:
            if cur: commits.append(cur)
            p=line.split("|",3); cur={"hash":p[0],"author":p[1],"date":p[2],"message":p[3],"files":[]}
        elif line.strip() and cur: cur["files"].append(line.strip())
    if cur: commits.append(cur)

    if fmt == "json": console.print_json(json.dumps(commits)); return

    t = Table(title=f"[bold]Changelog[/bold]  [dim]last {days} days · {len(commits)} commits[/dim]",
              box=box.SIMPLE_HEAD, border_style="cyan")
    t.add_column("Hash", style="cyan", width=8, no_wrap=True)
    t.add_column("Date", style="dim", width=12)
    t.add_column("Message", min_width=40)
    t.add_column("Files", justify="right", style="dim", width=6)
    for c in commits[:25]:
        t.add_row(c["hash"], c["date"], c["message"][:60], str(len(c["files"])))
    console.print(); console.print(t)


# ── doctor ────────────────────────────────────────────────────────────────────

@app.command("doctor")
def cmd_doctor():
    """Validate ContextOS setup — check all components."""
    import subprocess, socket
    print_logo()
    cfg_exists = (_root()/".contextos").exists()

    checks: list[tuple[bool,str,str]] = []

    # Python version
    import sys
    py_ok = sys.version_info >= (3,11)
    checks.append((py_ok, f"Python {sys.version.split()[0]}", "" if py_ok else "Python 3.11+ required"))

    # .contextos/
    checks.append((cfg_exists, ".contextos/ initialized", "Run: context init"))

    # pyproject installed
    try: import contextos; pkg_ok = True
    except: pkg_ok = False
    checks.append((pkg_ok, "contextos package installed", "Run: pip install -e ."))

    # LanceDB
    try: import lancedb; checks.append((True,"lancedb importable",""))
    except: checks.append((False,"lancedb importable","pip install lancedb"))

    # sentence-transformers
    try: import sentence_transformers; checks.append((True,"sentence-transformers importable",""))
    except: checks.append((False,"sentence-transformers importable","pip install sentence-transformers"))

    # model cached
    if cfg_exists:
        from contextos.config import load_config
        cfg = load_config()
        model_cached = any(cfg.embeddings_dir.rglob("config.json"))
        checks.append((model_cached,"Embedding model cached",
            "Run: context index  (downloads ~130MB on first run)"))

    # ripgrep
    try:
        subprocess.run(["rg","--version"], capture_output=True, check=True)
        checks.append((True,"ripgrep (rg) available — fast grep enabled",""))
    except:
        checks.append((True,"ripgrep not found — Python fallback active",
            "Install ripgrep for 10x faster grep: https://github.com/BurntSushi/ripgrep"))

    # server
    srv = False
    try:
        for port in (8080, 8765):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                srv = True
            s.close()
            if srv:
                break
    except Exception:
        pass
    checks.append((srv,"API server running","Run: context serve"))

    t = Table(title="[bold]ContextOS Doctor[/bold]", box=box.ROUNDED, border_style="cyan")
    t.add_column("", width=3)
    t.add_column("Check", style="bold")
    t.add_column("Note", style="dim")

    all_ok = True
    for ok_flag, label, hint in checks:
        if not ok_flag: all_ok = False
        icon = f"[success]{ICONS['success']}[/success]" if ok_flag else f"[warning]{ICONS['warning']}[/warning]"
        t.add_row(icon, label, hint)

    console.print(t)
    if all_ok:
        console.print(f"\n[success]{ICONS['success']} All checks passed. ContextOS is healthy.[/success]")
    else:
        console.print(f"\n[warning]{ICONS['warning']}  Some checks failed. Follow the hints above.[/warning]")


# ── cache commands ────────────────────────────────────────────────────────────

@cache_app.command("ls")
def cache_ls():
    """List cached chunk files."""
    cfg = _cfg()
    files = sorted(cfg.cache_dir.glob("*.json"), key=lambda x:-x.stat().st_size)
    if not files: empty_state("Cache is empty.","context index"); return
    t = Table(title="[bold]Chunk Cache[/bold]", box=box.ROUNDED, border_style="dim")
    t.add_column("File", style="dim"); t.add_column("Size", justify="right")
    for f in files[:20]: t.add_row(f.name[:40], _fmt_size(f.stat().st_size))
    if len(files)>20: t.add_row(f"[dim]…and {len(files)-20} more[/dim]","")
    console.print(); console.print(t)


@cache_app.command("clear")
def cache_clear():
    """Clear the chunk cache."""
    cfg = _cfg()
    count = sum(1 for f in cfg.cache_dir.glob("*.json") if f.unlink() or True)
    ok(f"Cleared {count} cached chunk files.")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
