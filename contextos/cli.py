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
def cmd_index(
    force: bool = typer.Option(False, "--force", "-f", help="Force re-index all documents, ignoring cache"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Index only a specific project"),
):
    """Build vector index, embeddings, and knowledge graph. Skips unchanged files."""
    from contextos.vault import load_registry, compute_changed_documents, update_hash_store
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

    # Load all documents from disk
    all_documents: list[Document] = []
    for rec in registry:
        if project and rec.get("project") != project:
            continue
        fp = Path(rec["filepath"])
        if not fp.exists(): warn(f"Missing: {fp.name}"); continue
        all_documents.append(Document(
            id=rec["id"], project=rec["project"], type=DocumentType(rec["type"]),
            domain=rec.get("domain"), status=DocumentStatus(rec.get("status","draft")),
            owner=rec.get("owner"),
            updated_at=date.fromisoformat(rec["updated_at"]) if rec.get("updated_at") else None,
            tags=rec.get("tags",[]), title=rec["title"], filepath=fp,
            content=fp.read_text(encoding="utf-8")))

    # Incremental change detection
    if force:
        to_process = all_documents
        new_count = len(all_documents)
        changed_count = 0
        unchanged_count = 0
    else:
        new_docs, changed_docs, unchanged_docs = compute_changed_documents(all_documents, cfg.metadata_dir)
        to_process = new_docs + changed_docs
        new_count = len(new_docs)
        changed_count = len(changed_docs)
        unchanged_count = len(unchanged_docs)

    if not to_process and not force:
        result_table = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
        result_table.add_column("k", style="dim", width=22); result_table.add_column("v", style="bold")
        result_table.add_row("Unchanged", f"[green]{unchanged_count}[/green] documents (skipped)")
        result_table.add_row("New / Changed", "0")
        result_table.add_row("Hint", "[dim]Use --force to re-index all[/dim]")
        console.print(Panel(result_table,
            title=f"[success]{ICONS['success']} Index Up-to-Date[/success]",
            border_style="green", padding=(0,1)))
        return

    doc_map = {d.id: d for d in all_documents}
    stats = {"docs": len(to_process), "chunks": 0, "nodes": 0, "edges": 0, "symbols": 0,
             "new": new_count, "changed": changed_count, "unchanged": unchanged_count}
    t_total = time.time()

    # Live updating panel
    def make_live_table(step: str, elapsed: float) -> Panel:
        t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
        t.add_column("k", style="dim", width=22); t.add_column("v", style="bold cyan")
        t.add_row("Step", step)
        t.add_row("Processing", f"{stats['docs']} docs  [dim]({stats['new']} new · {stats['changed']} changed · {stats['unchanged']} unchanged)[/dim]")
        t.add_row("Chunks", str(stats["chunks"]) if stats["chunks"] else "—")
        t.add_row("Graph Nodes", str(stats["nodes"]) if stats["nodes"] else "—")
        t.add_row("Graph Edges", str(stats["edges"]) if stats["edges"] else "—")
        if stats["symbols"]: t.add_row("Symbols", str(stats["symbols"]))
        t.add_row("Elapsed", f"{elapsed:.1f}s")
        return Panel(t, title=f"[cyan]{ICONS['spin']} Indexing Project[/cyan]", border_style="cyan", padding=(0,1))

    with Live(make_live_table("Chunking…", 0), console=console, refresh_per_second=4) as live:
        # Step 1: Chunk
        chunks_by_doc = chunk_all_documents(to_process, cfg.cache_dir)
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

        # Step 4: Graph (always rebuild from all_documents for correct edges)
        live.update(make_live_table("Building knowledge graph…", time.time()-t_total))
        gb = GraphBuilder(); gb.build(all_documents); gb.save(cfg.graph_dir)
        s = gb.get_summary(); stats["nodes"] = s["nodes"]; stats["edges"] = s["edges"]

        # Step 5: Symbol index (Python + JS/TS)
        live.update(make_live_table("Building symbol index…", time.time()-t_total))
        try:
            from contextos.symbols import build_symbol_index
            symbols_dir = cfg.contextos_dir / "symbols"
            sym_result = build_symbol_index(cfg.vault_paths, symbols_dir)
            stats["symbols"] = sym_result.get("symbols", 0)
        except Exception as exc:
            warn(f"Symbol index skipped: {exc}")
            stats["symbols"] = 0

        live.update(make_live_table("Complete", time.time()-t_total))

    elapsed = time.time()-t_total
    cfg.metadata_dir.mkdir(exist_ok=True)
    meta = cfg.metadata_dir/"index_meta.json"
    meta.write_text(json.dumps({"last_indexed":time.strftime("%Y-%m-%dT%H:%M:%S"),
        "document_count": len(all_documents),"chunk_count":written,"embedding_model":cfg.embedding_model},indent=2))

    # Save content hashes for incremental future runs
    update_hash_store(cfg.metadata_dir, to_process)

    # Invalidate context cache so stale results don't persist
    from contextos.cache_layer import invalidate_cache
    invalidate_cache()

    result_table = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    result_table.add_column("k", style="dim", width=22); result_table.add_column("v", style="bold")
    result_table.add_row("Project", cfg.project_name)
    result_table.add_row("New documents", f"[cyan]{new_count}[/cyan]")
    result_table.add_row("Changed documents", f"[cyan]{changed_count}[/cyan]")
    result_table.add_row("Unchanged (skipped)", f"[dim]{unchanged_count}[/dim]")
    result_table.add_row("Chunks generated", f"[cyan]{written:,}[/cyan]")
    result_table.add_row("Graph nodes", f"[cyan]{stats['nodes']}[/cyan]")
    result_table.add_row("Graph edges", f"[cyan]{stats['edges']}[/cyan]")
    if stats.get("symbols"): result_table.add_row("Symbols indexed", f"[cyan]{stats['symbols']:,}[/cyan]")
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
        import os, logging as _logging
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        _logging.getLogger("sentence_transformers").setLevel(_logging.ERROR)
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
def cmd_serve(
    port: int = typer.Option(8080, "--port"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Auto re-index vault files on change"),
):
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
    if watch:
        chk(f"Watch mode active  ({len(cfg.vault_paths)} vault paths)", bool(cfg.vault_paths))

    checks.add_section()
    checks.add_row(f"[success]{ICONS['server']}[/success]",
        f"[bold]Server Running  [cyan]http://127.0.0.1:{port}[/cyan][/bold]")
    checks.add_row("", f"[dim]Docs: http://127.0.0.1:{port}/docs[/dim]")
    checks.add_row("", f"[dim]Health: http://127.0.0.1:{port}/health[/dim]")
    if watch:
        checks.add_row("", "[dim]Watch: vault files auto-indexed on save[/dim]")
    checks.add_section()
    checks.add_row("[dim]⌨[/dim]", "[dim]Press Ctrl+C to stop[/dim]")

    console.print(Panel(checks, title="[bold]ContextOS Local Server[/bold]",
                        border_style="green", padding=(0,2)))

    # Start file watcher if requested
    if watch and cfg.vault_paths:
        from contextos.watcher import start_watcher, stop_watcher
        watcher = start_watcher(cfg)
        try:
            from contextos.api import run_server
            run_server(port=port)
        finally:
            watcher.stop()
    else:
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
    except Exception:
        pass

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
def token_create(
    name: str = typer.Argument(..., help="Label for this token"),
    scope: str = typer.Option("write", "--scope", "-s", help="Scope: read|write|admin"),
    expires: Optional[int] = typer.Option(None, "--expires", "-e", help="Expiry in days (default: never)"),
):
    """Generate a new API token with scope and optional expiry."""
    from contextos.auth import generate_token
    from contextos.schema import TokenScope
    brand_rule("token create")
    cfg = _cfg()

    try:
        token_scope = TokenScope(scope.lower())
    except ValueError:
        error_panel("Invalid Scope", scope, "Valid scopes: read | write | admin")
        raise typer.Exit(1)

    raw, token = generate_token(name, cfg.tokens_dir, scope=token_scope, expires_days=expires)

    t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    t.add_column("k", style="dim", width=10); t.add_column("v", style="bold")
    t.add_row("ID",       token.id)
    t.add_row("Name",     token.name)
    t.add_row("Scope",    f"[cyan]{token.scope.value}[/cyan]")
    t.add_row("Expires",  token.expires_at.strftime("%Y-%m-%d") if token.expires_at else "never")
    t.add_row("Created",  token.created_at.strftime("%Y-%m-%d %H:%M UTC"))
    t.add_section()
    t.add_row("Token",    f"[bold cyan]{raw}[/bold cyan]")
    t.add_row("",         "[dim]Copy now — never shown again[/dim]")

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
    t.add_column("Scope", width=8)
    t.add_column("Created", style="dim")
    t.add_column("Last Used", style="dim")
    t.add_column("Expires", style="dim")
    t.add_column("Status", width=10)
    for tk in tokens:
        lu = tk.last_used.strftime("%Y-%m-%d %H:%M") if tk.last_used else "—"
        st = f"[error]REVOKED[/error]" if tk.revoked else (
             f"[warning]EXPIRED[/warning]" if tk.is_expired() else
             f"[success]active[/success]")
        scope_str = tk.scope.value if tk.scope else "write"
        exp_str = tk.expires_at.strftime("%Y-%m-%d") if tk.expires_at else "never"
        t.add_row(tk.id, tk.name, scope_str, tk.created_at.strftime("%Y-%m-%d %H:%M"), lu, exp_str, st)

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
                    except Exception: pass
            except Exception: rg_ok = False

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
                except Exception: pass
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

    # Path containment check - prevent directory traversal
    root = _root()
    cfg_exists = (root / ".contextos").exists()
    if cfg_exists:
        try:
            from contextos.config import load_config
            cfg = load_config(root)
            allowed_roots = cfg.vault_paths + [root]
            # Check if file is within any allowed root
            contained = any(
                fp == allowed or fp.is_relative_to(allowed)
                for allowed in allowed_roots
            )
            if not contained:
                error_panel(
                    "Access Denied",
                    f"File is outside registered vault paths",
                    f"Allowed roots: {', '.join(str(p) for p in allowed_roots[:3])}"
                )
                raise typer.Exit(1)
        except (ImportError, typer.Exit):
            raise
        except Exception:
            pass  # If containment check fails, allow read (fail open for usability)

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


# ── context context (agent-facing) ───────────────────────────────────────────

@app.command("context")
def cmd_context(
    query: str = typer.Argument(..., help="Task or question to fetch context for"),
    project: Optional[str] = typer.Option(None, "-p", "--project"),
    max_tokens: int = typer.Option(4000, "--max-tokens", "-m"),
    raw: bool = typer.Option(False, "--raw", help="Print raw Markdown, no panel (pipe-friendly)"),
):
    """Assemble a context block for an agent task. The main pre-task command."""
    from contextos.embedder import Embedder
    from contextos.store import VectorStore
    from contextos.graph import GraphBuilder
    from contextos.retrieval import assemble_context
    brand_rule("context")
    cfg = _cfg()

    with console.status(f"[cyan]{ICONS['spin']} Assembling context…[/cyan]"):
        embedder = Embedder(cfg.embeddings_dir)
        store    = VectorStore(cfg.lancedb_dir)
        gb       = GraphBuilder(); gb.load(cfg.graph_dir)
        result   = assemble_context(
            query=query, embedder=embedder, store=store,
            graph_builder=gb, project=project, max_tokens=max_tokens,
        )

    if raw:
        # Plain output for piping to agents
        console.print(result.context)
        return

    # Rich panel display — use plain text, not Markdown renderer (avoids hangs on large content)
    preview = result.context[:2000]
    if len(result.context) > 2000:
        preview += f"\n\n[dim]… {len(result.context) - 2000} more chars — use --raw for full output[/dim]"

    sources_text = "\n".join(
        f"  [dim]•[/dim] [{type_style(s.get('type',''))}]{s.get('type','')}[/{type_style(s.get('type',''))}]  {s.get('title','')}"
        for s in result.sources[:8]
    )
    if len(result.sources) > 8:
        sources_text += f"\n  [dim]…and {len(result.sources)-8} more[/dim]"

    console.print(Panel(
        preview,
        title=f"[bold]Retrieved Context[/bold]  [dim]~{result.token_estimate} tokens · {len(result.sources)} sources[/dim]",
        border_style="cyan", padding=(0, 2)
    ))
    if sources_text:
        console.print(Panel(sources_text, title="[dim]Sources[/dim]", border_style="dim", padding=(0,2)))


# ── context diff ─────────────────────────────────────────────────────────────

@app.command("diff")
def cmd_diff():
    """Show what changed in the vault since the last index run."""
    from contextos.vault import load_registry, load_hash_store
    brand_rule("diff")
    cfg = _cfg()
    registry = load_registry(cfg.metadata_dir)
    if not registry:
        empty_state("No vault registered.", "context import <path>"); raise typer.Exit(0)

    stored_hashes = load_hash_store(cfg.metadata_dir)

    new_files, changed_files, missing_files = [], [], []
    for rec in registry:
        fp = Path(rec["filepath"])
        if not fp.exists():
            missing_files.append(rec); continue
        current_hash = __import__("hashlib").sha256(fp.read_bytes()).hexdigest()
        doc_id = rec["id"]
        if doc_id not in stored_hashes:
            new_files.append(rec)
        elif stored_hashes[doc_id] != current_hash:
            changed_files.append(rec)

    if not new_files and not changed_files and not missing_files:
        ok("Vault is up-to-date with the index. Nothing to re-index.")
        return

    t = Table(title="[bold]Vault Diff[/bold]  [dim]since last index[/dim]",
              box=box.ROUNDED, border_style="cyan")
    t.add_column("Status", width=12)
    t.add_column("File", style="bold")
    t.add_column("Project", style="dim")

    for r in new_files:
        t.add_row(f"[green]new[/green]", Path(r["filepath"]).name, r.get("project",""))
    for r in changed_files:
        t.add_row(f"[yellow]changed[/yellow]", Path(r["filepath"]).name, r.get("project",""))
    for r in missing_files:
        t.add_row(f"[red]missing[/red]", Path(r["filepath"]).name, r.get("project",""))

    console.print(); console.print(t)
    total = len(new_files) + len(changed_files)
    if total:
        next_action("context index", f"{total} file(s) need re-indexing")


# ── context projects ──────────────────────────────────────────────────────────

@app.command("projects")
def cmd_projects():
    """List all registered projects with document counts and index status."""
    from contextos.vault import load_registry, load_hash_store
    brand_rule("projects")
    cfg = _cfg()
    registry = load_registry(cfg.metadata_dir)
    if not registry:
        empty_state("No vaults registered.", "context import <path>"); raise typer.Exit(0)

    stored_hashes = load_hash_store(cfg.metadata_dir)
    projects: dict[str, dict] = {}
    for rec in registry:
        p = rec.get("project", "unknown")
        if p not in projects:
            projects[p] = {"docs": 0, "indexed": 0, "stale": 0}
        projects[p]["docs"] += 1
        fp = Path(rec["filepath"])
        if fp.exists():
            current = __import__("hashlib").sha256(fp.read_bytes()).hexdigest()
            if rec["id"] in stored_hashes and stored_hashes[rec["id"]] == current:
                projects[p]["indexed"] += 1
            else:
                projects[p]["stale"] += 1

    t = Table(title="[bold]Registered Projects[/bold]", box=box.ROUNDED, border_style="cyan")
    t.add_column("Project", style="bold cyan")
    t.add_column("Documents", justify="right")
    t.add_column("Indexed", justify="right", style="green")
    t.add_column("Stale", justify="right", style="yellow")
    t.add_column("Status", width=14)

    for name, stats in sorted(projects.items()):
        if stats["stale"] == 0 and stats["indexed"] > 0:
            status = f"[success]{ICONS['success']} current[/success]"
        elif stats["stale"] > 0:
            status = f"[warning]{ICONS['warning']} needs index[/warning]"
        else:
            status = f"[error]{ICONS['error']} not indexed[/error]"
        t.add_row(name, str(stats["docs"]), str(stats["indexed"]), str(stats["stale"]), status)

    console.print(); console.print(t)


# ── context about ─────────────────────────────────────────────────────────────

@app.command("about")
def cmd_about():
    """Show version, architecture, and license information."""
    print_logo()
    t = Table(show_header=False, box=box.ROUNDED, border_style="cyan", min_width=52, padding=(0,1))
    t.add_column("k", style="dim", width=20); t.add_column("v", style="bold")
    t.add_row("Version", f"v{VERSION}")
    t.add_row("License", "MIT")
    t.add_row("Architecture", "3-layer: Vault → Index → API")
    t.add_row("Embedding model", "BAAI/bge-small-en-v1.5 (384-dim)")
    t.add_row("Vector store", "LanceDB (local, embedded)")
    t.add_row("Graph engine", "NetworkX (JSON persistence)")
    t.add_row("API binding", "127.0.0.1 only — never 0.0.0.0")
    t.add_row("Network at runtime", "Zero — fully offline after model download")
    t.add_row("Repository", "github.com/AbhayankarBellur/ContextOS")
    console.print(t)


# ── context symbols ───────────────────────────────────────────────────────────

@app.command("symbols")
def cmd_symbols(
    query: str = typer.Argument(..., help="Symbol name to search (function, class, method)"),
    sym_type: Optional[str] = typer.Option(None, "--type", "-t", help="function|class|method"),
    file_filter: Optional[str] = typer.Option(None, "--file", "-f", help="File path substring filter"),
    limit: int = typer.Option(20, "--limit", "-n"),
    fmt: str = typer.Option("text", "--format"),
):
    """Search the AST symbol index for functions, classes, and methods."""
    from contextos.symbols import search_symbols
    brand_rule("symbols")
    cfg = _cfg()
    symbols_dir = cfg.contextos_dir / "symbols"

    if not (symbols_dir / "index.json").exists():
        empty_state(
            "Symbol index not built yet.",
            "context index    (builds symbols automatically)"
        )
        raise typer.Exit(0)

    results = search_symbols(
        query=query, symbols_dir=symbols_dir,
        sym_type=sym_type, file_pattern=file_filter, limit=limit,
    )

    if fmt == "json":
        console.print_json(json.dumps(results, indent=2)); return

    if not results:
        empty_state(f'No symbols matching "{query}"', f'context symbols "{query}" --type function')
        return

    t = Table(
        title=f"[bold]Symbols[/bold]  [dim]{query}[/dim]  [dim]{len(results)} results[/dim]",
        box=box.ROUNDED, border_style="cyan"
    )
    t.add_column("Name", style="bold cyan", min_width=22)
    t.add_column("Type", style="dim", width=10)
    t.add_column("Signature", min_width=40)
    t.add_column("Line", justify="right", style="dim", width=6)
    t.add_column("File", style="dim")

    for r in results:
        file_short = "/".join(Path(r.get("file","")).parts[-2:])
        sig = r.get("signature","")[:60]
        t.add_row(
            r.get("name",""),
            r.get("type",""),
            sig,
            str(r.get("line_start","")),
            file_short,
        )

    console.print(); console.print(t)

    # Expand first result
    if results:
        first = results[0]
        docstring = first.get("docstring","")
        body = f"[bold]{first.get('signature','')}[/bold]"
        if docstring:
            body += f"\n\n[dim]{docstring[:200]}[/dim]"
        body += f"\n\n[dim]{first.get('file','')}  :{first.get('line_start','')}–{first.get('line_end','')}[/dim]"
        console.print(Panel(body,
            title=f"[bold]Best match — {first.get('name','')}[/bold]",
            border_style="cyan", padding=(0,2)))


# ── context mcp ───────────────────────────────────────────────────────────────

@app.command("mcp")
def cmd_mcp():
    """Start the MCP server (stdio transport) for native agent tool integration.

    Add to your agent's mcp.json:

      {
        "mcpServers": {
          "contextos": {
            "command": "context",
            "args": ["mcp"],
            "env": { "CONTEXTOS_TOKEN": "<your-token>" }
          }
        }
      }
    """
    from contextos.mcp_server import run_mcp_server
    run_mcp_server()


# ── context setup ─────────────────────────────────────────────────────────────

@app.command("setup")
def cmd_setup(
    agent: str = typer.Argument(..., help="Agent to configure: kiro|claude|cursor|continue|cline|aider|copilot|all"),
):
    """Write agent-specific integration config files for zero-friction setup."""
    brand_rule("setup")
    cfg = _cfg()
    root = _root()
    written = []

    # Get token hint
    from contextos.auth import list_tokens
    tokens = list_tokens(cfg.tokens_dir)
    token_hint = tokens[0].id + "..." if tokens else "ctx_YOUR_TOKEN_HERE"

    def write(path: Path, content: str, label: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            warn(f"{label} already exists — skipping (delete to regenerate)")
            return
        path.write_text(content)
        written.append(str(path.relative_to(root)))

    # mcp.json — works for all MCP-compatible agents
    mcp_content = json.dumps({
        "mcpServers": {
            "contextos": {
                "command": "context",
                "args": ["mcp"],
                "env": {"CONTEXTOS_TOKEN": token_hint}
            }
        }
    }, indent=2)

    cursor_rules = (
        "# ContextOS Integration\n"
        "Before every task, retrieve context from ContextOS:\n\n"
        "curl -s -X POST http://127.0.0.1:8080/context \\\n"
        '  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        "  -d '{\"query\": \"<your task>\", \"project\": \"<project-name>\"}'\n\n"
        "After completing a task: run `context index` to update the knowledge graph.\n"
    )

    continue_config = json.dumps({
        "models": [],
        "contextProviders": [{
            "name": "http",
            "params": {
                "url": "http://127.0.0.1:8080/context",
                "title": "ContextOS",
                "description": "Local project knowledge vault"
            }
        }]
    }, indent=2)

    copilot_instructions = (
        "# ContextOS — Project Memory\n\n"
        "Before starting any task, call the ContextOS context API:\n\n"
        "```bash\n"
        "curl -s -X POST http://127.0.0.1:8080/context \\\n"
        "  -H 'Authorization: Bearer $CONTEXTOS_TOKEN' \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        "  -d '{\"query\": \"<task>\", \"project\": \"<project>\"}'\n"
        "```\n\n"
        "See AGENTS.md for full integration guide.\n"
    )

    targets = {
        "kiro":     [(root / ".kiro" / "hooks" / "contextos-prefetch.json", None, "Kiro hook")],
        "cursor":   [(root / ".cursorrules", cursor_rules, "Cursor rules")],
        "continue": [(root / ".continue" / "config.json", continue_config, "Continue.dev config")],
        "copilot":  [(root / ".github" / "copilot-instructions.md", copilot_instructions, "Copilot instructions")],
        "mcp":      [(root / "mcp.json", mcp_content, "MCP config (all agents)")],
    }
    # Claude and Cline are already handled by CLAUDE.md + AGENTS.md

    if agent == "all":
        all_targets = [item for items in targets.values() for item in items]
    else:
        all_targets = targets.get(agent, [])
        if not all_targets:
            error_panel("Unknown Agent", agent, f"Valid: {', '.join(targets.keys())} | all")
            raise typer.Exit(1)

    for path, content, label in all_targets:
        if content:
            write(path, content, label)

    if written:
        t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
        t.add_column("ic", width=3); t.add_column("path")
        for w in written:
            t.add_row(f"[success]{ICONS['success']}[/success]", w)
        console.print(Panel(t,
            title=f"[success]{ICONS['success']} Integration Files Written[/success]",
            border_style="green", padding=(0,1)))
        console.print()
        info(f"Set your token: [bold]export CONTEXTOS_TOKEN=<your-token>[/bold]")
        info("Start the server: [bold]context serve[/bold]")
    else:
        warn("No new files written — all targets already exist.")


# ── session commands ──────────────────────────────────────────────────────────

session_app = typer.Typer(help="Agent session tracking and memory")
app.add_typer(session_app, name="session")

@session_app.command("start")
def session_start(name: Optional[str] = typer.Option(None, "--name", "-n", help="Session label")):
    """Start a new agent session for tracking context and decisions."""
    from contextos.session import create_session
    brand_rule("session start")
    cfg = _cfg()
    sessions_dir = cfg.contextos_dir / "sessions"
    s = create_session(sessions_dir, name)
    t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    t.add_column("k", style="dim", width=14); t.add_column("v", style="bold")
    t.add_row("Session ID",   s["id"])
    t.add_row("Name",         s["name"])
    t.add_row("Started",      s["started_at"][:19])
    console.print(Panel(t, title=f"[success]{ICONS['success']} Session Started[/success]",
                        border_style="green", padding=(0,2)))
    console.print(f"\n  [dim]Track events:[/dim]  [bold]context session event {s['id']} <type> <text>[/bold]")
    console.print(f"  [dim]End session:[/dim]   [bold]context session end {s['id']}[/bold]")


@session_app.command("end")
def session_end(
    session_id: str = typer.Argument(..., help="Session ID to end"),
    export: bool = typer.Option(True, "--export/--no-export", help="Export summary to vault"),
):
    """End a session, generate summary, optionally export to vault."""
    from contextos.session import end_session
    cfg = _cfg()
    sessions_dir = cfg.contextos_dir / "sessions"
    vault_dir    = cfg.vault_paths[0] / "context" if cfg.vault_paths else None
    try:
        s = end_session(sessions_dir, session_id, vault_export_dir=vault_dir if export else None)
    except ValueError as e:
        error_panel("Session Error", str(e)); raise typer.Exit(1)
    summary = s.get("summary", {})
    t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    t.add_column("k", style="dim", width=22); t.add_column("v", style="bold")
    t.add_row("Duration",        summary.get("duration","—"))
    t.add_row("Events",          str(summary.get("total_events",0)))
    t.add_row("Searches",        str(len(summary.get("searches",[]))))
    t.add_row("Files changed",   str(len(summary.get("files_changed",[]))))
    t.add_row("Tasks completed", str(len(summary.get("tasks_completed",[]))))
    if export and vault_dir:
        t.add_row("Vault export",    "✓ written to vault/context/")
    console.print(Panel(t, title=f"[success]{ICONS['success']} Session Ended[/success]",
                        border_style="green", padding=(0,2)))


@session_app.command("event")
def session_event(
    session_id: str = typer.Argument(..., help="Session ID"),
    event_type: str = typer.Argument(..., help="Type: task_started|task_completed|decision_made|note|file_changed"),
    text: str = typer.Argument(..., help="Event description or text"),
):
    """Log an event to an active session."""
    from contextos.session import add_event
    cfg = _cfg()
    sessions_dir = cfg.contextos_dir / "sessions"
    ok_flag = add_event(sessions_dir, session_id, event_type, {"text": text, "task": text})
    if ok_flag:
        ok(f"Event logged: [{event_type}] {text[:60]}")
    else:
        error_panel("Event Failed", f"Session {session_id} not found or already ended")
        raise typer.Exit(1)


@session_app.command("list")
def session_list():
    """List recent agent sessions."""
    from contextos.session import list_sessions
    brand_rule("session list")
    cfg = _cfg()
    sessions_dir = cfg.contextos_dir / "sessions"
    sessions = list_sessions(sessions_dir, limit=15)
    if not sessions:
        empty_state("No sessions yet.", "context session start"); return
    t = Table(title="[bold]Agent Sessions[/bold]", box=box.ROUNDED, border_style="cyan")
    t.add_column("ID", style="cyan", width=10)
    t.add_column("Name", style="bold")
    t.add_column("Started", style="dim")
    t.add_column("Duration", style="dim", width=10)
    t.add_column("Events", justify="right", width=8)
    t.add_column("Status", width=10)
    for s in sessions:
        summary  = s.get("summary") or {}
        dur      = summary.get("duration","—")
        ended    = s.get("ended_at")
        status   = f"[success]ended[/success]" if ended else f"[green]active[/green]"
        t.add_row(s["id"], s.get("name",""), s.get("started_at","")[:16],
                  dur, str(len(s.get("events",[]))), status)
    console.print(); console.print(t)


@session_app.command("summary")
def session_summary(
    session_id: Optional[str] = typer.Argument(None, help="Session ID (default: last session)"),
):
    """Show summary of a session. Defaults to the most recent session."""
    from contextos.session import get_session, get_last_session
    brand_rule("session summary")
    cfg = _cfg()
    sessions_dir = cfg.contextos_dir / "sessions"
    s = get_session(sessions_dir, session_id) if session_id else get_last_session(sessions_dir)
    if not s:
        empty_state("No session found.", "context session list"); return

    summary = s.get("summary") or {}
    t = Table(show_header=False, box=box.ROUNDED, border_style="cyan", min_width=52, padding=(0,1))
    t.add_column("k", style="dim", width=22); t.add_column("v", style="bold")
    t.add_row("Session", s.get("name",""))
    t.add_row("ID", s["id"])
    t.add_row("Started", s.get("started_at","")[:19])
    t.add_row("Duration", summary.get("duration","—"))
    t.add_row("Total events", str(summary.get("total_events",0)))
    console.print(Panel(t, title="[bold]Session Summary[/bold]", border_style="cyan"))

    if summary.get("tasks_completed"):
        console.print("\n[bold]Tasks completed:[/bold]")
        for task in summary["tasks_completed"]:
            console.print(f"  [success]{ICONS['success']}[/success] {task}")

    if summary.get("decisions"):
        console.print("\n[bold]Decisions made:[/bold]")
        for d in summary["decisions"]:
            console.print(f"  [cyan]•[/cyan] {d}")

    if summary.get("files_changed"):
        console.print("\n[bold]Files changed:[/bold]")
        for f in summary["files_changed"]:
            console.print(f"  [dim]{f}[/dim]")

    if summary.get("searches"):
        console.print("\n[bold]Searches:[/bold]")
        for q in summary["searches"][:8]:
            console.print(f"  [dim]›[/dim] {q}")


# ── context pull (connectors) ─────────────────────────────────────────────────

@app.command("pull")
def cmd_pull(
    connector: str = typer.Argument(..., help="Connector: github | openapi | json"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source: repo, file path, or URL"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name to tag docs with"),
    pull_type: Optional[str] = typer.Option(None, "--type", "-t", help="Connector-specific type filter"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory (default: .contextos/pulled/)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite unchanged files"),
):
    """Pull external data into the vault. Supports: github, openapi, json."""
    from contextos.connectors import CONNECTORS
    brand_rule("pull")
    cfg = _cfg()

    conn_cls = CONNECTORS.get(connector.lower())
    if not conn_cls:
        error_panel("Unknown Connector", connector,
                    f"Available: {', '.join(CONNECTORS.keys())}")
        raise typer.Exit(1)

    proj = project or cfg.project_name
    conn_config: dict = {}
    if source:      conn_config["source"] = source
    if source:      conn_config["repo"]   = source   # github alias
    if pull_type:   conn_config["type"]   = pull_type

    conn = conn_cls(project=proj, config=conn_config)

    out_dir = Path(output) if output else (cfg.contextos_dir / "pulled" / connector / proj)

    with console.status(f"[cyan]{ICONS['spin']} Pulling from {connector}…[/cyan]"):
        try:
            result = conn.pull(out_dir, force=force)
        except Exception as exc:
            error_panel("Pull Failed", str(exc),
                        f"Check your config for the {connector} connector")
            raise typer.Exit(1)

    t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    t.add_column("k", style="dim", width=16); t.add_column("v", style="bold")
    t.add_row("Connector",   connector)
    t.add_row("Project",     result["project"])
    t.add_row("Total docs",  str(result["total"]))
    t.add_row("Written",     f"[green]{result['written']}[/green]")
    t.add_row("Skipped",     f"[dim]{result['skipped']} (unchanged)[/dim]")
    t.add_row("Output dir",  str(result["output_dir"]))

    console.print(Panel(t, title=f"[success]{ICONS['success']} Pull Complete — {connector}[/success]",
                        border_style="green", padding=(0,1)))

    if result["written"] > 0:
        next_action(f"context import {out_dir}  &&  context index",
                    "Import and index the pulled documents")


# ── context export ────────────────────────────────────────────────────────────

@app.command("export")
def cmd_export(
    project: str = typer.Argument(..., help="Project name to export"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option("markdown", "--format", help="Format: markdown | json"),
):
    """Export an entire project vault as a single Markdown or JSON file."""
    brand_rule("export")
    cfg = _cfg()
    from contextos.vault import load_registry
    registry = load_registry(cfg.metadata_dir)
    project_docs = [r for r in registry if r.get("project") == project]

    if not project_docs:
        empty_state(f'No documents found for project "{project}"',
                    "context projects"); raise typer.Exit(0)

    out_path = Path(output) if output else Path(f"{project}-export.{'md' if fmt=='markdown' else 'json'}")

    with console.status(f"[cyan]{ICONS['spin']} Exporting {len(project_docs)} docs…[/cyan]"):
        if fmt == "json":
            import datetime
            export_data = {"project": project, "exported_at": datetime.datetime.now().isoformat(),
                           "documents": []}
            for rec in project_docs:
                fp = Path(rec["filepath"])
                export_data["documents"].append({
                    "title": rec["title"], "type": rec["type"],
                    "filepath": rec["filepath"],
                    "content": fp.read_text(encoding="utf-8") if fp.exists() else ""
                })
            out_path.write_text(json.dumps(export_data, indent=2))
        else:
            # Single Markdown file
            lines = [f"# {project} — Vault Export\n",
                     f"*Exported {__import__('time').strftime('%Y-%m-%d %H:%M')} — {len(project_docs)} documents*\n\n---\n"]
            for rec in sorted(project_docs, key=lambda r: (r.get("type",""), r.get("title",""))):
                fp = Path(rec["filepath"])
                if fp.exists():
                    lines.append(f"\n\n## {rec['title']}\n\n")
                    lines.append(f"*Type: {rec['type']} | File: {fp.name}*\n\n")
                    # Strip frontmatter for export
                    content = fp.read_text(encoding="utf-8")
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        content = parts[2].strip() if len(parts) >= 3 else content
                    lines.append(content)
                    lines.append("\n\n---")
            out_path.write_text("\n".join(lines), encoding="utf-8")

    console.print(Panel(
        f"  [dim]Project:[/dim]   [bold]{project}[/bold]\n"
        f"  [dim]Documents:[/dim] [bold]{len(project_docs)}[/bold]\n"
        f"  [dim]Format:[/dim]    [bold]{fmt}[/bold]\n"
        f"  [dim]Output:[/dim]    [bold cyan]{out_path}[/bold cyan]\n"
        f"  [dim]Size:[/dim]      [bold]{_fmt_size(out_path.stat().st_size)}[/bold]",
        title=f"[success]{ICONS['success']} Export Complete[/success]",
        border_style="green", padding=(0,2)))


# ── context dashboard ─────────────────────────────────────────────────────────

@app.command("dashboard")
def cmd_dashboard():
    """Launch the full-screen Textual TUI dashboard."""
    cfg = _cfg()
    from contextos.dashboard import run_dashboard
    run_dashboard(cfg)


# ── context start (one-command bootstrap) ────────────────────────────────────

@app.command("start")
def cmd_start(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name"),
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Vault path (existing or new)"),
    template: str = typer.Option("default", "--template", "-t", help="Vault template if creating new"),
    port: int = typer.Option(8080, "--port", help="API server port"),
    skip_serve: bool = typer.Option(False, "--no-serve", help="Skip starting the API server"),
):
    """
    One-command bootstrap. Initialises, imports, indexes, and starts the server.
    This is the recommended entry point for new users.

      context start
      context start --name my-api --vault ./docs

    """
    print_logo()
    from contextos.config import get_contextos_dir, save_config, Config
    from contextos.vault import scan_vault, write_registry
    from contextos.auth import generate_token
    from contextos.schema import TokenScope

    root = _root()
    console.print(Panel(
        "[dim]Setting up ContextOS in one command.\n"
        "This will initialise, import your vault, index it, create a token, and start the server.[/dim]",
        border_style="cyan", padding=(0,2)
    ))
    console.print()

    # Step 1 — Get project name interactively if not supplied
    if not name:
        name = typer.prompt("  Project name", default=root.name)

    # Step 2 — Vault path
    if not vault:
        vault_default = str(root / "docs" / "vault")
        vault = typer.prompt("  Vault path (existing dir, or new to scaffold)", default=vault_default)

    vault_path = Path(vault).resolve()

    # Step 3 — Init
    with console.status("[cyan]Initialising .contextos/…[/cyan]"):
        cfg = Config(root=root, project_name=name)
        for d in [cfg.contextos_dir, cfg.embeddings_dir, cfg.lancedb_dir,
                  cfg.graph_dir, cfg.tokens_dir, cfg.cache_dir, cfg.logs_dir, cfg.metadata_dir]:
            d.mkdir(parents=True, exist_ok=True)
        save_config(cfg)
        gi = root / ".gitignore"
        if gi.exists():
            if ".contextos/" not in gi.read_text():
                gi.open("a").write("\n.contextos/\n")
        else:
            gi.write_text(".contextos/\n")
    ok(f"Initialized [bold]{cfg.contextos_dir}[/bold]")

    # Step 4 — Scaffold vault if it doesn't exist
    if not vault_path.exists() or not any(vault_path.iterdir()):
        with console.status(f"[cyan]Scaffolding vault from '{template}' template…[/cyan]"):
            from contextos.scaffolder import scaffold_vault
            created = scaffold_vault(vault_path, template_name=template, variables={
                "project_name": name, "team": "engineering", "domain_name": "core",
            })
        ok(f"Vault scaffolded: [bold]{len(created)}[/bold] files at [bold]{vault_path}[/bold]")
    else:
        ok(f"Using existing vault: [bold]{vault_path}[/bold]")

    # Step 5 — Import vault
    with console.status("[cyan]Scanning vault documents…[/cyan]"):
        docs = scan_vault(vault_path)
        if docs:
            cfg.vault_paths = [vault_path]
            registry_path = write_registry(docs, cfg.metadata_dir)
            save_config(cfg)
    ok(f"Imported [bold]{len(docs)}[/bold] documents")

    if not docs:
        warn("No documents found. Add Markdown files to your vault and run [cyan]context index[/cyan].")
        raise typer.Exit(0)

    # Step 6 — Index
    console.print()
    console.rule("[cyan]Building index[/cyan]", style="cyan")
    from contextos.vault import compute_changed_documents, update_hash_store
    from contextos.chunker import chunk_all_documents
    from contextos.embedder import Embedder
    from contextos.store import VectorStore
    from contextos.graph import GraphBuilder
    from contextos.schema import Document, DocumentType, DocumentStatus
    from datetime import date as _date

    all_docs: list[Document] = []
    registry = docs  # docs already parsed

    for doc in registry:
        all_docs.append(doc)

    doc_map = {d.id: d for d in all_docs}

    with console.status("[cyan]Chunking…[/cyan]"):
        chunks_by_doc = chunk_all_documents(all_docs, cfg.cache_dir)

    console.print(f"  [dim]Chunking:[/dim] {sum(len(v) for v in chunks_by_doc.values())} chunks")

    embedder = Embedder(cfg.embeddings_dir)
    all_chunks = [c for cl in chunks_by_doc.values() for c in cl]

    with Progress(SpinnerColumn(), TextColumn("[cyan]Embedding…[/cyan]"), BarColumn(bar_width=28),
                  TaskProgressColumn(), console=console, transient=True) as prog:
        task = prog.add_task("e", total=len(all_chunks))
        BATCH = 32
        texts = [c.content for c in all_chunks]
        for i in range(0, len(all_chunks), BATCH):
            bt = texts[i:i+BATCH]; bc = all_chunks[i:i+BATCH]
            vecs = embedder.embed(bt)
            for c, v in zip(bc, vecs): c.embedding = v
            prog.advance(task, len(bc))

    with console.status("[cyan]Writing to LanceDB…[/cyan]"):
        store = VectorStore(cfg.lancedb_dir)
        written = store.upsert_chunks(all_chunks, doc_map)
        gb = GraphBuilder(); gb.build(all_docs); gb.save(cfg.graph_dir)
        # Build symbol index
        try:
            from contextos.symbols import build_symbol_index
            build_symbol_index(cfg.vault_paths, cfg.contextos_dir / "symbols")
        except Exception:
            pass
        update_hash_store(cfg.metadata_dir, all_docs)

    import time as _time
    cfg.metadata_dir.mkdir(exist_ok=True)
    (cfg.metadata_dir / "index_meta.json").write_text(json.dumps({
        "last_indexed": _time.strftime("%Y-%m-%dT%H:%M:%S"),
        "document_count": len(all_docs), "chunk_count": written,
        "embedding_model": cfg.embedding_model,
    }, indent=2))

    ok(f"Indexed [bold]{written}[/bold] chunks from [bold]{len(all_docs)}[/bold] documents")

    # Step 7 — Token
    with console.status("[cyan]Creating API token…[/cyan]"):
        raw_token, token = generate_token(f"{name}-agent", cfg.tokens_dir, scope=TokenScope.write)

    console.print()
    console.print(Panel(
        f"[dim]Token (save this — shown once):[/dim]\n\n"
        f"  [bold cyan]{raw_token}[/bold cyan]\n\n"
        f"  [dim]export CONTEXTOS_TOKEN={raw_token}[/dim]",
        title=f"[success]{ICONS['success']} Token Created[/success]",
        border_style="green", padding=(0,2)
    ))

    from contextos.cache_layer import invalidate_cache
    invalidate_cache()

    if skip_serve:
        console.print()
        ok(f"[bold]{name}[/bold] is ready.")
        next_action(f"context serve --port {port}", "Start the API server when ready")
        return

    # Step 8 — Serve
    console.print()
    console.print(Panel(
        f"[bold green]{ICONS['success']} {name} is ready.[/bold green]\n\n"
        f"  [dim]Server:[/dim]  [bold]http://127.0.0.1:{port}[/bold]\n"
        f"  [dim]Health:[/dim]  [bold]http://127.0.0.1:{port}/health[/bold]\n"
        f"  [dim]Docs:[/dim]    [bold]http://127.0.0.1:{port}/docs[/bold]\n\n"
        f"  [dim]Token set:[/dim]  export CONTEXTOS_TOKEN={raw_token[:20]}…\n\n"
        f"  [dim yellow]Ctrl+C to stop[/dim yellow]",
        title="[bold]ContextOS Ready[/bold]", border_style="green", padding=(0,2)
    ))
    from contextos.api import run_server
    run_server(port=port)


# ── context eval ──────────────────────────────────────────────────────────────

@app.command("eval")
def cmd_eval(
    questions: str = typer.Option("eval/questions.json", "--questions", "-q",
                                   help="Path to eval questions JSON file"),
    output: Optional[str] = typer.Option(None, "--output", "-o",
                                          help="Save results to JSON file"),
    k: int = typer.Option(5, "--k", help="Top-K for Hit Rate calculation"),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    hybrid: bool = typer.Option(True, "--hybrid/--no-hybrid",
                                 help="Use hybrid search (BM25 + vector)"),
    alpha: float = typer.Option(0.7, "--alpha", help="Hybrid vector weight (0=BM25, 1=vector)"),
):
    """
    Evaluate retrieval quality against a golden question set.

    Measures Hit Rate @K, MRR, avg top-1 score, and latency.
    Use this to tune hybrid search alpha, chunk size, or embedding quality.

    Example:
      context eval --questions eval/questions.json --k 5
    """
    from contextos.evaluator import load_questions, run_eval, save_results, EvalQuestion
    from contextos.embedder import Embedder
    from contextos.store import VectorStore
    brand_rule("eval")
    cfg = _cfg()

    q_path = Path(questions)
    if not q_path.exists():
        # Try the example file
        example = Path("eval/questions.json.example")
        if example.exists():
            warn(f"Questions file not found. Using example: {example}")
            q_path = example
        else:
            error_panel("Questions File Not Found", str(q_path),
                        "Create eval/questions.json or use --questions path")
            raise typer.Exit(1)

    with console.status("[cyan]Loading questions…[/cyan]"):
        eval_questions = load_questions(q_path)
        # Override k if specified
        for q in eval_questions:
            q.k = k
            if project:
                q.project = project

    console.print(f"  [dim]Loaded {len(eval_questions)} questions[/dim]")
    console.print(f"  [dim]Mode: {'hybrid (BM25 + vector)' if hybrid else 'vector only'} · alpha={alpha}[/dim]\n")

    with console.status(f"[cyan]{ICONS['spin']} Running evaluation…[/cyan]"):
        embedder = Embedder(cfg.embeddings_dir)
        store    = VectorStore(cfg.lancedb_dir)
        summary  = run_eval(eval_questions, embedder, store,
                            use_hybrid=hybrid, hybrid_alpha=alpha)

    # Results table per question
    t = Table(
        title=f"[bold]Retrieval Evaluation[/bold]  [dim]{len(eval_questions)} questions · @{k}[/dim]",
        box=box.ROUNDED, border_style="cyan"
    )
    t.add_column("Query", min_width=30, no_wrap=False)
    t.add_column("Expected", style="dim", min_width=20)
    t.add_column("Hit", width=5, justify="center")
    t.add_column("Rank", width=5, justify="right")
    t.add_column("Score", width=7, justify="right")
    t.add_column("ms", width=6, justify="right", style="dim")

    for r in summary.results:
        hit_icon  = f"[success]{ICONS['success']}[/success]" if r.hit else f"[error]{ICONS['error']}[/error]"
        rank_str  = str(r.rank) if r.rank > 0 else "—"
        score_str = f"[{score_style(r.top1_score)}]{r.top1_score:.2f}[/{score_style(r.top1_score)}]"
        t.add_row(
            r.question.query[:45],
            r.question.expected_title[:28],
            hit_icon, rank_str, score_str, str(r.latency_ms)
        )

    console.print(t)

    # Summary panel
    hr_color  = "green" if summary.hit_rate >= 0.8 else "yellow" if summary.hit_rate >= 0.6 else "red"
    mrr_color = "green" if summary.mrr >= 0.7     else "yellow" if summary.mrr >= 0.5     else "red"

    st = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    st.add_column("k", style="dim", width=22); st.add_column("v", style="bold")
    st.add_row("Hit Rate @K",      f"[{hr_color}]{summary.hit_rate:.1%}[/{hr_color}]")
    st.add_row("MRR",              f"[{mrr_color}]{summary.mrr:.3f}[/{mrr_color}]")
    st.add_row("Avg top-1 score",  f"{summary.avg_top1_score:.3f}")
    st.add_row("No-result queries",f"[{'red' if summary.no_result_pct > 0 else 'green'}]{summary.no_result_pct:.1%}[/{'red' if summary.no_result_pct > 0 else 'green'}]")
    st.add_row("Avg latency",      f"{summary.avg_latency_ms:.0f} ms")
    st.add_row("Search mode",      "hybrid (BM25+vector)" if hybrid else "vector only")

    console.print(Panel(st, title="[bold]Summary[/bold]", border_style="cyan", padding=(0,1)))

    if output:
        out_path = Path(output)
        save_results(summary, out_path)
        ok(f"Results saved to [bold]{out_path}[/bold]")
    else:
        info("Use [cyan]--output eval/results.json[/cyan] to save detailed results")


# ── vault sub-commands ────────────────────────────────────────────────────────

vault_app = typer.Typer(help="Vault scaffolding and validation")
app.add_typer(vault_app, name="vault")

@vault_app.command("init")
def vault_init(
    path: str = typer.Argument(..., help="Target directory for the new vault"),
    template: str = typer.Option("default", "--template", "-t", help="Template: default|microservice|api-first"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name"),
    team: Optional[str] = typer.Option(None, "--team", help="Team or owner name"),
):
    """Scaffold a new vault from a template with pre-filled document stubs."""
    from contextos.scaffolder import scaffold_vault, list_templates
    brand_rule("vault init")
    target = Path(path).resolve()

    variables = {
        "project_name": project or target.name,
        "team":         team or "engineering",
        "domain_name":  "core",
    }

    with console.status(f"[cyan]{ICONS['spin']} Scaffolding vault from '{template}' template…[/cyan]"):
        try:
            created = scaffold_vault(target, template_name=template, variables=variables)
        except ValueError as exc:
            avail = ", ".join(list_templates().keys())
            error_panel("Template Not Found", str(exc), f"Available: {avail}")
            raise typer.Exit(1)

    t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    t.add_column("k", style="dim", width=16); t.add_column("v", style="bold")
    t.add_row("Template",  template)
    t.add_row("Location",  str(target))
    t.add_row("Files created", str(len(created)))
    for f in created[:8]:
        t.add_row("", f"[dim]{f.relative_to(target)}[/dim]")
    if len(created) > 8:
        t.add_row("", f"[dim]…and {len(created)-8} more[/dim]")

    console.print(Panel(t, title=f"[success]{ICONS['success']} Vault Scaffolded[/success]",
                        border_style="green", padding=(0,1)))
    next_action(f"context import {target}  &&  context index", "Import and index the new vault")


@vault_app.command("validate")
def vault_validate(
    path: str = typer.Argument(".", help="Vault path to validate"),
    fix_hints: bool = typer.Option(True, "--hints/--no-hints"),
):
    """Validate vault documents for frontmatter compliance."""
    from contextos.scaffolder import validate_vault
    brand_rule("vault validate")
    vault_path = Path(path).resolve()

    with console.status(f"[cyan]{ICONS['spin']} Validating {vault_path.name}…[/cyan]"):
        result = validate_vault(vault_path)

    t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    t.add_column("k", style="dim", width=18); t.add_column("v", style="bold")
    t.add_row("Valid documents", f"[green]{result['valid']}[/green]")
    t.add_row("Errors",          f"[red]{len(result['errors'])}[/red]" if result['errors'] else "[green]0[/green]")
    t.add_row("Warnings",        f"[yellow]{len(result['warnings'])}[/yellow]" if result['warnings'] else "[green]0[/green]")

    border = "green" if not result["errors"] else "red"
    title_icon = ICONS["success"] if not result["errors"] else ICONS["error"]
    title_color = "success" if not result["errors"] else "error"
    console.print(Panel(t,
        title=f"[{title_color}]{title_icon} Vault Validation — {vault_path.name}[/{title_color}]",
        border_style=border, padding=(0,1)))

    if result["errors"] and fix_hints:
        console.print("\n[bold red]Errors (must fix):[/bold red]")
        for e in result["errors"][:10]:
            console.print(f"  [red]{ICONS['error']}[/red] [dim]{e['file']}[/dim] — {e['issue']}")

    if result["warnings"] and fix_hints:
        console.print("\n[bold yellow]Warnings (recommended):[/bold yellow]")
        for w in result["warnings"][:10]:
            console.print(f"  [yellow]{ICONS['warning']}[/yellow] [dim]{w['file']}[/dim] — {w['issue']}")

    if result["errors"]:
        raise typer.Exit(1)


@vault_app.command("templates")
def vault_templates():
    """List available vault templates."""
    from contextos.scaffolder import list_templates
    brand_rule("vault templates")
    templates = list_templates()
    t = Table(title="[bold]Available Templates[/bold]", box=box.ROUNDED, border_style="cyan")
    t.add_column("Name", style="bold cyan"); t.add_column("Description")
    for name, desc in templates.items():
        t.add_row(name, desc)
    console.print(); console.print(t)
    console.print(f"\n[dim]Usage: [bold]context vault init ./my-vault --template <name>[/bold][/dim]")


# ── plugin commands ───────────────────────────────────────────────────────────

plugin_app = typer.Typer(help="Manage ContextOS connector plugins")
app.add_typer(plugin_app, name="plugin")

@plugin_app.command("list")
def plugin_list():
    """List all available connectors: built-in and installed plugins."""
    from contextos.plugins import list_plugins
    brand_rule("plugin list")
    plugins = list_plugins()
    t = Table(title="[bold]Available Connectors[/bold]", box=box.ROUNDED, border_style="cyan")
    t.add_column("Name", style="bold cyan", width=14)
    t.add_column("Source", style="dim", width=10)
    t.add_column("Description")
    for p in plugins:
        source_color = {"builtin": "dim", "global": "green", "local": "yellow", "package": "blue"}.get(p.source, "dim")
        t.add_row(p.name, f"[{source_color}]{p.source}[/{source_color}]", p.description)
    console.print(); console.print(t)
    console.print(f"\n[dim]Usage: [bold]context pull <name> --source ...[/bold][/dim]")


@plugin_app.command("install")
def plugin_install(
    package: str = typer.Argument(..., help="Package name or path to install"),
    upgrade: bool = typer.Option(False, "--upgrade", "-U"),
):
    """Install a connector plugin from PyPI or a local path."""
    from contextos.plugins import install_plugin
    brand_rule("plugin install")
    with console.status(f"[cyan]{ICONS['spin']} Installing {package}…[/cyan]"):
        success = install_plugin(package, upgrade=upgrade)
    if success:
        ok(f"Plugin installed: [bold]{package}[/bold]")
        info("Run [cyan]context plugin list[/cyan] to verify.")
    else:
        error_panel("Install Failed", f"Could not install: {package}",
                    "Check package name and internet connection")
        raise typer.Exit(1)


# ── logs command ──────────────────────────────────────────────────────────────

@app.command("logs")
def cmd_logs(
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
    log_type: str = typer.Option("app", "--type", "-t", help="Log type: app|slow|audit"),
    fmt: str = typer.Option("text", "--format", help="Output format: text|json"),
):
    """Show structured logs: app, slow queries, or audit trail."""
    from contextos.logger import get_logger
    brand_rule("logs")
    cfg = _cfg()
    logger_inst = get_logger(cfg.logs_dir)
    records = logger_inst.tail_log(lines=tail, log_type=log_type)

    if not records:
        empty_state(f"No {log_type} logs yet.", "context serve  # then make some requests")
        return

    if fmt == "json":
        console.print_json(json.dumps(records, indent=2))
        return

    t = Table(
        title=f"[bold]{log_type.title()} Log[/bold]  [dim]{len(records)} entries[/dim]",
        box=box.SIMPLE_HEAD, border_style="cyan"
    )
    t.add_column("Time", style="dim", width=20, no_wrap=True)
    t.add_column("Type", width=12)
    t.add_column("Details", min_width=40)

    for r in records[-tail:]:
        ts       = r.get("ts","")[:19].replace("T"," ")
        rtype    = r.get("type","")
        color    = {"request":"cyan","error":"red","slow_query":"yellow","audit":"magenta","index_op":"green"}.get(rtype,"dim")

        if rtype == "request":
            details = f"{r.get('method','')} {r.get('endpoint','')} [{r.get('status','')}] {r.get('latency_ms','')}ms"
        elif rtype == "index_op":
            details = f"{r.get('operation','')} docs={r.get('doc_count','')} chunks={r.get('chunk_count','')} {r.get('duration_s','')}s"
        elif rtype == "audit":
            details = f"token={r.get('token_name','')} {r.get('method','')} {r.get('endpoint','')} {r.get('latency_ms','')}ms"
        else:
            details = r.get("message","") or str(r)[:80]

        t.add_row(ts, f"[{color}]{rtype}[/{color}]", details)

    console.print(); console.print(t)


# ── ci sub-commands ───────────────────────────────────────────────────────────

ci_app = typer.Typer(help="CI/CD integration commands")
app.add_typer(ci_app, name="ci")

@ci_app.command("check")
def ci_check(
    path: str = typer.Option(".", "--vault", help="Vault path to check"),
):
    """CI validation: exit 1 if vault has errors, orphans, or stale index. Zero output on success."""
    from contextos.scaffolder import validate_vault
    from contextos.vault import load_registry, load_hash_store
    import sys

    vault_path = Path(path).resolve()
    issues = []

    # 1. Validate frontmatter
    result = validate_vault(vault_path)
    if result["errors"]:
        for e in result["errors"]:
            issues.append(f"FRONTMATTER_ERROR: {e['file']}: {e['issue']}")

    # 2. Check stale index
    ctx_dir = _root() / ".contextos"
    if ctx_dir.exists():
        from contextos.config import load_config
        cfg = load_config()
        registry = load_registry(cfg.metadata_dir)
        hashes   = load_hash_store(cfg.metadata_dir)
        stale = 0
        for rec in registry:
            fp = Path(rec["filepath"])
            if fp.exists():
                import hashlib
                h = hashlib.sha256(fp.read_bytes()).hexdigest()
                if rec["id"] not in hashes or hashes[rec["id"]] != h:
                    stale += 1
        if stale > 0:
            issues.append(f"STALE_INDEX: {stale} document(s) not indexed — run context index")

    if issues:
        for issue in issues:
            console.print(f"[red]{ICONS['error']}[/red] {issue}")
        raise typer.Exit(1)
    else:
        console.print(f"[green]{ICONS['success']}[/green] All checks passed")


@ci_app.command("index")
def ci_index():
    """Headless index for CI: JSON progress to stdout, exit 0/1."""
    import sys
    cfg = _cfg()
    from contextos.vault import load_registry, compute_changed_documents, update_hash_store
    from contextos.chunker import chunk_all_documents
    from contextos.embedder import Embedder
    from contextos.store import VectorStore
    from contextos.graph import GraphBuilder
    from contextos.schema import Document, DocumentType, DocumentStatus
    from datetime import date

    registry = load_registry(cfg.metadata_dir)
    if not registry:
        console.print_json(json.dumps({"status": "error", "message": "No vault registered"}))
        raise typer.Exit(1)

    all_docs: list[Document] = []
    for rec in registry:
        fp = Path(rec["filepath"])
        if not fp.exists(): continue
        all_docs.append(Document(
            id=rec["id"], project=rec["project"], type=DocumentType(rec["type"]),
            domain=rec.get("domain"), status=DocumentStatus(rec.get("status","draft")),
            owner=rec.get("owner"),
            updated_at=date.fromisoformat(rec["updated_at"]) if rec.get("updated_at") else None,
            tags=rec.get("tags",[]), title=rec["title"], filepath=fp,
            content=fp.read_text(encoding="utf-8")))

    new_docs, changed_docs, unchanged = compute_changed_documents(all_docs, cfg.metadata_dir)
    to_process = new_docs + changed_docs

    if not to_process:
        console.print_json(json.dumps({"status": "ok", "message": "Index up-to-date",
                                        "unchanged": len(unchanged)}))
        return

    import time as _time; t0 = _time.time()
    doc_map = {d.id: d for d in all_docs}
    chunks_by_doc = chunk_all_documents(to_process, cfg.cache_dir)
    embedder = Embedder(cfg.embeddings_dir)
    all_chunks = [c for cl in chunks_by_doc.values() for c in cl]
    vecs = embedder.embed([c.content for c in all_chunks])
    for c, v in zip(all_chunks, vecs): c.embedding = v
    store = VectorStore(cfg.lancedb_dir)
    written = store.upsert_chunks(all_chunks, doc_map)
    gb = GraphBuilder(); gb.build(all_docs); gb.save(cfg.graph_dir)
    update_hash_store(cfg.metadata_dir, to_process)
    elapsed = _time.time() - t0

    from contextos.cache_layer import invalidate_cache
    invalidate_cache()

    console.print_json(json.dumps({
        "status": "ok", "new": len(new_docs), "changed": len(changed_docs),
        "unchanged": len(unchanged), "chunks": written, "elapsed_s": round(elapsed, 2)
    }))


# ── context cache stats ───────────────────────────────────────────────────────

@cache_app.command("stats")
def cache_stats():
    """Show context response cache hit/miss statistics."""
    from contextos.cache_layer import get_cache
    brand_rule("cache stats")
    stats = get_cache().stats()
    t = Table(title="[bold]Context Cache[/bold]", show_header=False, box=box.ROUNDED, border_style="cyan")
    t.add_column("k", style="dim", width=18); t.add_column("v", style="bold")
    t.add_row("Hits",         f"[green]{stats['hits']}[/green]")
    t.add_row("Misses",       f"[yellow]{stats['misses']}[/yellow]")
    t.add_row("Hit rate",     f"[cyan]{stats['hit_rate_pct']}%[/cyan]")
    t.add_row("Entries",      f"{stats['size']} / {stats['max_size']}")
    t.add_row("TTL",          f"{stats['ttl_seconds']}s")
    console.print(); console.print(t)


# ── user memory commands ──────────────────────────────────────────────────────

umem_app = typer.Typer(help="Cross-app user memory — write and query persistent user knowledge")
app.add_typer(umem_app, name="memory-user")

@umem_app.command("write")
def umem_write(
    user_id:   str = typer.Argument(..., help="User identifier (email, username, UUID)"),
    content:   str = typer.Argument(..., help="Memory content to store"),
    mem_type:  str = typer.Option("fact", "--type", "-t", help="fact|preference|decision|event"),
    importance:int = typer.Option(3, "--importance", "-i", help="1-5 (5=critical)"),
    source:    str = typer.Option("user", "--source", help="Source client name"),
    project:   Optional[str] = typer.Option(None, "--project", "-p"),
    supersedes:Optional[str] = typer.Option(None, "--supersedes", help="Fragment ID this replaces"),
):
    """Store a memory fragment for a user. Persists across all AI coding sessions."""
    from contextos.user_memory import write_fragment
    from contextos.embedder import Embedder
    brand_rule("memory-user write")
    cfg = _cfg()
    embedder = Embedder(cfg.embeddings_dir)
    fragment = write_fragment(
        memory_dir=cfg.contextos_dir / "memory",
        user_id=user_id, content=content, fragment_type=mem_type,
        importance=importance, source_client=source,
        project=project, supersedes_id=supersedes,
    )
    t = Table(show_header=False, box=box.SIMPLE, padding=(0,1))
    t.add_column("k", style="dim", width=14); t.add_column("v", style="bold")
    t.add_row("ID",        fragment["id"])
    t.add_row("User",      fragment["user_id"])
    t.add_row("Type",      fragment["type"])
    t.add_row("Importance", str(fragment["importance"]) + "/5")
    t.add_row("Source",    fragment["source_client"])
    console.print(Panel(t, title=f"[success]{ICONS['success']} Memory Stored[/success]",
                        border_style="green", padding=(0,2)))


@umem_app.command("query")
def umem_query(
    user_id:    str = typer.Argument(...),
    query:      str = typer.Argument(...),
    mem_type:   Optional[str] = typer.Option(None, "--type", "-t"),
    limit:      int = typer.Option(10, "--limit", "-n"),
    project:    Optional[str] = typer.Option(None, "--project", "-p"),
    min_imp:    int = typer.Option(1, "--min-importance"),
):
    """Query memory fragments for a user, ranked by importance × decay × similarity."""
    from contextos.user_memory import query_fragments
    from contextos.embedder import Embedder
    brand_rule("memory-user query")
    cfg = _cfg()
    embedder = Embedder(cfg.embeddings_dir)

    with console.status(f"[cyan]{ICONS['spin']} Querying memory…[/cyan]"):
        results = query_fragments(
            memory_dir=cfg.contextos_dir / "memory",
            user_id=user_id, query=query, embedder=embedder,
            project=project, fragment_type=mem_type,
            limit=limit, min_importance=min_imp,
        )

    if not results:
        empty_state(f"No memory found for user '{user_id}'",
                    f'context memory-user write {user_id} "your memory here"')
        return

    t = Table(title=f"[bold]Memory for {user_id}[/bold]  [dim]{query}[/dim]",
              box=box.ROUNDED, border_style="cyan")
    t.add_column("Type", style="cyan", width=12)
    t.add_column("Content", min_width=40)
    t.add_column("Imp", justify="center", width=5)
    t.add_column("Score", justify="right", width=8)
    t.add_column("Decay", justify="right", width=7, style="dim")
    t.add_column("Source", style="dim", width=12)

    for r in results:
        score = r.get("_score", 0)
        decay = r.get("_decay", 1)
        sc = f"[{score_style(score)}]{score:.3f}[/{score_style(score)}]"
        t.add_row(r.get("type",""), r.get("content","")[:55],
                  str(r.get("importance",3)), sc, f"{decay:.2f}", r.get("source_client",""))

    console.print(); console.print(t)


@umem_app.command("list")
def umem_list(user_id: str = typer.Argument(...)):
    """List all memory fragments for a user."""
    from contextos.user_memory import _read_fragments_from_file
    brand_rule("memory-user list")
    cfg = _cfg()
    fragments = _read_fragments_from_file(cfg.contextos_dir / "memory", user_id)
    active = [f for f in fragments if f.get("active", True)]
    if not active:
        empty_state(f"No memory for '{user_id}'", f"context memory-user write {user_id} \"...\"")
        return
    t = Table(title=f"[bold]Memory — {user_id}[/bold]  [dim]{len(active)} fragments[/dim]",
              box=box.ROUNDED, border_style="cyan")
    t.add_column("ID", style="dim", width=18, no_wrap=True)
    t.add_column("Type", style="cyan", width=12)
    t.add_column("Imp", width=5, justify="center")
    t.add_column("Content", min_width=40)
    t.add_column("Created", style="dim", width=12)
    for fr in active:
        t.add_row(fr["id"], fr.get("type",""), str(fr.get("importance",3)),
                  fr.get("content","")[:60], fr.get("created_at","")[:10])
    console.print(); console.print(t)


@umem_app.command("stats")
def umem_stats(user_id: str = typer.Argument(...)):
    """Show memory statistics for a user."""
    from contextos.user_memory import get_stats
    brand_rule("memory-user stats")
    cfg = _cfg()
    stats = get_stats(cfg.contextos_dir / "memory", user_id)
    t = Table(show_header=False, box=box.ROUNDED, border_style="cyan", min_width=40, padding=(0,1))
    t.add_column("k", style="dim", width=20); t.add_column("v", style="bold")
    t.add_row("User ID",         stats["user_id"])
    t.add_row("Total fragments", str(stats["total_fragments"]))
    t.add_row("Active",          f"[green]{stats['active_fragments']}[/green]")
    t.add_row("Superseded",      f"[dim]{stats['superseded']}[/dim]")
    t.add_row("Oldest",          str(stats.get("oldest","—"))[:10])
    t.add_row("Newest",          str(stats.get("newest","—"))[:10])
    console.print(Panel(t, title=f"[bold]User Memory Stats[/bold]", border_style="cyan"))
    if stats.get("by_type"):
        console.print("\n[bold]By type:[/bold]")
        for mtype, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
            console.print(f"  [cyan]{mtype:<14}[/cyan] {count}")


@umem_app.command("delete")
def umem_delete(
    user_id: str = typer.Argument(...),
    confirm: bool = typer.Option(False, "--yes", "-y"),
):
    """GDPR bulk delete: remove ALL memory for a user permanently."""
    from contextos.user_memory import delete_user_memory
    cfg = _cfg()
    if not confirm:
        warn(f"This permanently deletes ALL memory for user [bold]{user_id}[/bold].")
        typer.confirm("Proceed?", abort=True)
    with console.status(f"[cyan]{ICONS['spin']} Deleting memory for {user_id}…[/cyan]"):
        result = delete_user_memory(cfg.contextos_dir / "memory", user_id)
    ok(f"Deleted [bold]{result['deleted_fragments']}[/bold] fragments for {user_id}")


# ── context suggest ───────────────────────────────────────────────────────────

@app.command("suggest")
def cmd_suggest(
    task: str = typer.Argument(..., help="Task description to get suggestions for"),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    limit: int = typer.Option(5, "--limit", "-n"),
):
    """
    Suggest implementation approaches based on past decisions in vault + session history.
    Queries ADRs, workflows, and session decisions for similar tasks.
    """
    from contextos.embedder import Embedder
    from contextos.store import VectorStore
    brand_rule("suggest")
    cfg = _cfg()

    with console.status(f"[cyan]{ICONS['spin']} Searching past decisions…[/cyan]"):
        embedder = Embedder(cfg.embeddings_dir)
        store    = VectorStore(cfg.lancedb_dir)
        qv       = embedder.embed_query(task)

        # Search ADRs and context docs
        adrs = store.search(query_vector=qv, project=project, type_filter="adr", limit=3)
        ctx  = store.search(query_vector=qv, project=project, type_filter="context", limit=2)
        all_results = adrs + ctx

    if not all_results:
        empty_state("No past decisions found.", "context index  # then try again")
        return

    console.print(f"\n[bold]Suggestions for:[/bold] [cyan]\"{task}\"[/cyan]\n")

    # Past decisions
    if adrs:
        console.print("[bold]Past Architecture Decisions:[/bold]")
        for r in adrs:
            score = max(0.0, 1.0 - float(r.get("_distance", 1)))
            snippet = r.get("content","")[:200].replace("\n"," ")
            console.print(Panel(
                f"[dim]{r.get('heading','')}[/dim]\n\n{snippet}…\n\n[dim]{r.get('filepath','')}[/dim]",
                title=f"[magenta]{r.get('title','')}[/magenta]  [dim]{score:.2f}[/dim]",
                border_style="magenta", padding=(0,1)
            ))

    # Approach suggestions (A/B/C from context)
    if ctx:
        console.print("\n[bold]Relevant Context:[/bold]")
        for r in ctx:
            snippet = r.get("content","")[:150].replace("\n"," ")
            console.print(f"  [cyan]{ICONS['bullet']}[/cyan] [dim]{r.get('title','')}:[/dim] {snippet}…")

    next_action("context session event <id> decision_made \"<your choice>\"",
                "Log your decision so future sessions can learn from it")


# ── proxy commands ────────────────────────────────────────────────────────────

proxy_app_typer = typer.Typer(help="Context proxy — sit between IDE and LLM, auto-compress context")
app.add_typer(proxy_app_typer, name="proxy")

@proxy_app_typer.command("start")
def proxy_start(
    target: str = typer.Option("https://api.openai.com", "--target", "-t",
                                help="LLM API to proxy to"),
    port:   int = typer.Option(9137, "--port", help="Local proxy port"),
    project:Optional[str] = typer.Option(None, "--project", "-p"),
):
    """
    Start the ContextOS context proxy on 127.0.0.1:9137.

    Point your IDE API base URL to http://127.0.0.1:9137 instead of the LLM directly.
    The proxy will auto-compress old context turns and inject vault knowledge.

    Cursor:  Settings → API Base URL → http://127.0.0.1:9137/v1
    Continue.dev: models[].apiBase = "http://127.0.0.1:9137"
    """
    brand_rule("proxy start")
    cfg_root = _root()
    console.print(Panel(
        f"[bold green]ContextOS Context Proxy[/bold green]\n\n"
        f"  [dim]Listening:[/dim]  [bold]http://127.0.0.1:{port}[/bold]\n"
        f"  [dim]Target:[/dim]     [bold]{target}[/bold]\n"
        f"  [dim]Project:[/dim]    [bold]{project or 'all'}[/bold]\n\n"
        f"  [dim]IDE config:[/dim]\n"
        f"    API Base URL → [cyan]http://127.0.0.1:{port}/v1[/cyan]\n\n"
        f"  [dim]What the proxy does:[/dim]\n"
        f"  [dim]• HOT (last 5 turns) — kept verbatim[/dim]\n"
        f"  [dim]• WARM (turns 6-15) — kept verbatim[/dim]\n"
        f"  [dim]• COLD (older turns) — compressed with TF-IDF[/dim]\n"
        f"  [dim]• DEAD (duplicates/empty) — dropped silently[/dim]\n"
        f"  [dim]• Vault context injected before each request[/dim]\n\n"
        f"  [dim yellow]Ctrl+C to stop[/dim yellow]",
        title="[bold]ContextOS Proxy[/bold]", border_style="cyan", padding=(0,2)
    ))
    from contextos.proxy import run_proxy
    run_proxy(port=port, target=target, project=project, vault_root=cfg_root)


@proxy_app_typer.command("status")
def proxy_status(port: int = typer.Option(9137, "--port")):
    """Show proxy statistics — tokens saved, turn classifications."""
    import socket
    brand_rule("proxy status")
    try:
        s = socket.socket(); s.settimeout(0.5)
        running = s.connect_ex(("127.0.0.1", port)) == 0
        s.close()
    except Exception:
        running = False

    if not running:
        empty_state(f"Proxy not running on port {port}.",
                    f"context proxy start --port {port}")
        return

    try:
        import urllib.request as _ur
        data = json.loads(_ur.urlopen(f"http://127.0.0.1:{port}/proxy/stats", timeout=2).read())
        t = Table(show_header=False, box=box.ROUNDED, border_style="cyan", padding=(0,1))
        t.add_column("k", style="dim", width=22); t.add_column("v", style="bold")
        t.add_row("Status",          "[green]running[/green]")
        t.add_row("Total requests",  str(data.get("requests", 0)))
        t.add_row("Total tokens saved", f"{data.get('tokens_saved_total',0):,}")
        console.print(Panel(t, title="[bold]Proxy Status[/bold]", border_style="cyan"))

        sessions = data.get("sessions", [])[-5:]
        if sessions:
            console.print("\n[bold]Recent sessions:[/bold]")
            for s in sessions:
                heat = s.get("heat", {})
                console.print(f"  [{s['ts']}] saved={s.get('saved',0)} tokens "
                              f"({s.get('compression',0)}%) "
                              f"HOT={heat.get('hot',0)} WARM={heat.get('warm',0)} "
                              f"COLD={heat.get('cold',0)} DEAD={heat.get('dead',0)}")
    except Exception as exc:
        warn(f"Could not read proxy stats: {exc}")


# ── cache commands ────────────────────────────────────────────────────────────

@cache_app.command("ls")
def cache_ls():
    """List cached chunk files."""
    cfg = _cfg()
    files = sorted(cfg.cache_dir.glob("*.json"), key=lambda x: -x.stat().st_size)
    if not files:
        empty_state("Cache is empty.", "context index"); return
    t = Table(title="[bold]Chunk Cache[/bold]", box=box.ROUNDED, border_style="dim")
    t.add_column("File", style="dim"); t.add_column("Size", justify="right")
    for f in files[:20]:
        t.add_row(f.name[:40], _fmt_size(f.stat().st_size))
    if len(files) > 20:
        t.add_row(f"[dim]…and {len(files)-20} more[/dim]", "")
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
