<div align="center">

```
  _____            _            _    ___  ____
 / ____|          | |          | |  / _ \/ ___|
| |     ___  _ __ | |_ _____  _| |_| | | \___ \
| |    / _ \| '_ \| __/ _ \ \/ / __| | | |___) |
| |___| (_) | | | | ||  __/>  <| |_| |_| |___) |
 \_____\___/|_| |_|\__\___/_/\_\\__|\___/|____/
```

**Local-first knowledge OS for AI coding agents.**

[![Tests](https://img.shields.io/badge/tests-199%20passing-brightgreen)](tests/)
[![Version](https://img.shields.io/badge/version-2.0.0-blue)](pyproject.toml)
[![PyPI](https://img.shields.io/pypi/v/contextos-vault)](https://pypi.org/project/contextos-vault/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/contextos-vault)](https://pypi.org/project/contextos-vault/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

</div>

---

ContextOS gives AI coding agents **structured, searchable project memory** — architecture decisions, domain models, workflows, and sprint context — via a **localhost-only HTTP API**. Agents retrieve exactly what they need before every task, eliminating repeated context and architectural drift.

**Zero cloud. Zero tracking. Zero API keys. Works fully offline after first model download.**

---

## Why ContextOS?

Every AI session starts from zero. You explain your architecture. Again. You paste the same domain model. Again. Your agent drifts from last week's decisions. Again.

**ContextOS fixes this permanently.**

```
Without ContextOS                   With ContextOS
──────────────────────────────────────────────────────────
Re-explain architecture every chat  Agent queries vault, knows it already
Paste domain models manually        Retrieved automatically before every task
Agent ignores past decisions        ADRs surfaced with decay-scored relevance
Token waste on repeated context     4000-token precision context block
Context drift across sessions       Session memory + decision trail indexed
Different LLMs lose your prefs      Cross-app user memory by user_id
```

**Measured results (real numbers from `context eval`):**

| Metric | Vector only | Hybrid BM25+Vector | Delta |
|---|---|---|---|
| Avg top-1 score | 0.537 | **1.000** | **+86%** |
| Search latency | 4,386ms | **37ms** | **-119x** |
| Hit Rate @5 | 100% | 100% | — |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1 — Vault (Filesystem)                                   │
│  Plain Markdown + YAML frontmatter. Human-readable. Editable.   │
│  Supports: .md, .pdf, .docx, .pptx                              │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2 — Index (Local Process)                                │
│  BAAI/bge-small-en-v1.5 embeddings (384-dim, CPU)               │
│  LanceDB vector store + BM25 keyword index (hybrid search)      │
│  NetworkX knowledge graph (nodes + edges from doc relationships) │
│  All stored in .contextos/ — rebuildable at any time            │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3 — API (localhost only)                                 │
│  FastAPI on 127.0.0.1:8080. Never exposed to network.           │
│  Bearer token auth with scopes (read / write / admin)           │
│  MCP server for native agent tool integration                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quickstart — One Command

```bash
# Install from PyPI
pip install contextos-vault

# OR clone and install from source
git clone https://github.com/AbhayankarBellur/ContextOS.git
cd ContextOS
pip install -e .
context start
```

`context start` is an interactive wizard that does everything:

```
? Project name: my-project
? Vault path (or create new): ./docs/vault
? Template: default

  ✓ Initialized .contextos/
  ✓ Vault scaffolded (6 files)
  ✓ Vault imported (6 documents)
  ⟳ Indexing... (downloads ~130MB model once, then fully offline)
  ✓ Indexed 6 documents, 22 chunks
  ✓ Token created: ctx_abc123...  (save this)
  ✓ Server started on http://127.0.0.1:8080

  ContextOS is ready.
```

That's it. Your agent can now call `POST /context` with any task description and receive structured, prioritised project knowledge.

---

## Manual Quickstart (4 commands)

```bash
pip install -e .
context init
context import ./docs/vault
context index
context serve
```

---

## Installation

**Requirements:** Python 3.11+

```bash
# Install from PyPI (recommended)
pip install contextos-vault

# Verify
context doctor
```

**Or install from source (for development / contributions):**
```bash
git clone https://github.com/AbhayankarBellur/ContextOS.git
cd ContextOS
pip install -e ".[dev]"
context doctor
```

**First `context index` run** downloads the ~130MB BAAI/bge-small-en-v1.5 embedding model. All subsequent runs are **fully offline** — no internet required.

### Optional: faster grep

Install [ripgrep](https://github.com/BurntSushi/ripgrep) for `context grep` performance:
```bash
# Windows (winget)
winget install BurntSushi.ripgrep.MSVC
# macOS
brew install ripgrep
# Linux
apt install ripgrep
```

---

## Vault Structure

A vault is a directory of Markdown files (plus PDF/DOCX/PPTX) with YAML frontmatter. ContextOS scaffolds the structure for you:

```
my-project/
  product/
    vision.md          # Product vision, goals, success metrics
    requirements.md
  architecture/
    overview.md        # System architecture, tech stack
    backend.md
    api.md
  domain/
    customer.md        # One file per domain entity
    booking.md
    payment.md
  decisions/
    ADR-001-postgres.md    # Architecture Decision Records
    ADR-002-events.md
  workflows/
    booking-flow.md    # End-to-end process flows
    refund-flow.md
  context/
    current-sprint.md  # Updated each sprint — the most important file
    backlog.md
```

### Frontmatter Schema

Every document carries YAML frontmatter:

```yaml
---
project: my-project
type: architecture          # architecture | adr | domain | workflow | product | context | note
domain: booking             # optional — omit if cross-domain
status: approved            # draft | approved | deprecated
owner: engineering          # optional team/person label
updated_at: 2026-06-04
tags:
  - booking
  - api
---

# Your Document Title

Content here...
```

**Required fields:** `project`, `type`, `status`  
**Recommended:** `updated_at`, `tags`

---

## All CLI Commands

### Core Commands

| Command | Description |
|---|---|
| `context start` | **One-command bootstrap** — init + scaffold + import + index + token + serve |
| `context init` | Initialize `.contextos/` in current directory |
| `context import <path>` | Register a vault directory and scan all documents |
| `context index` | Build vector + BM25 + graph index (skips unchanged files) |
| `context search "<query>"` | Semantic search across the indexed vault |
| `context serve` | Start API server on `127.0.0.1:8080` |
| `context status` | Show index health, server status, vault info |

### Agent Commands

| Command | Description |
|---|---|
| `context context "<task>"` | Assemble a ready-to-paste context block for an agent task |
| `context context "<task>" --raw` | Plain Markdown output for piping to agents |
| `context context "<task>" --max-tokens 4000` | Set token budget |
| `context eval --questions eval/questions.json` | Evaluate retrieval quality (Hit Rate, MRR) |
| `context mcp` | Start MCP server (stdio transport) for native agent tool integration |

### Code Intelligence

| Command | Description |
|---|---|
| `context grep "<pattern>"` | Fast regex search across codebase (ripgrep if available) |
| `context grep "<pattern>" --path ./src --type py` | Filter by directory and extension |
| `context grep "<pattern>" --literal` | Exact string search (no regex) |
| `context symbols "<name>"` | Search AST symbol index (functions, classes, methods) |
| `context symbols "create_" --type function` | Filter by symbol type |
| `context read <file>` | Read a file with metadata |
| `context read <file> --lines 40:80` | Read specific line range |
| `context read <file> --format meta` | Show file metadata (size, language, hash) |
| `context tree` | Project directory tree with file stats |
| `context tree --depth 2` | Control tree depth |
| `context changelog` | Recent git commit history |
| `context diff` | What changed in vault since last index |

### Token Management

```bash
context token create <name>                    # Generate a new token (shown once)
context token create <name> --scope read       # Read-only token (for CI agents)
context token create <name> --scope admin      # Admin token (for operators)
context token create <name> --expires 30       # Token expires in 30 days
context token list                             # List all tokens (raw values never shown)
context token revoke <token-id>                # Immediately revoke a token
```

**Token scopes:**
- `read` — search, context, documents, graph (use for CI and untrusted agents)
- `write` — index, pull, import, session write (trusted agents, default)
- `admin` — token management, audit log, memory reset (operators only)

### Session Tracking

```bash
context session start                          # Start a new agent session
context session start --name "sprint-12-work"
context session event <id> task_completed "Implemented booking cancellation"
context session event <id> decision_made "Use Stripe refunds, not manual"
context session event <id> file_changed "src/payment.py"
context session end <id>                       # End session, generate summary
context session end <id> --no-export           # Don't write to vault
context session list                           # List recent sessions
context session summary                        # Show last session summary
context session summary <id>                   # Show specific session
```

Sessions auto-export a Markdown summary to `vault/context/session-<date>-<id>.md`, which gets indexed and searchable in future sessions — creating a persistent memory trail.

### Memory Management

```bash
context memory status                          # Disk usage breakdown
context memory projects                        # List indexed projects with sizes
context memory purge <project> --yes           # Remove project from index (vault untouched)
context memory archive <project> --yes         # Archive index to .tar.gz, then purge
context memory clear-embeddings --yes          # Delete model cache (~130MB), re-downloads on next index
context memory reset --yes                     # Full reset of .contextos/ (vault untouched)
context memory reset --wipe-tokens --yes       # Reset including tokens
```

### Vault Scaffolding

```bash
context vault init ./my-vault                  # Scaffold default template
context vault init ./my-service --template microservice
context vault init ./my-api --template api-first
context vault init ./my-vault --project payments --team platform
context vault validate ./my-vault              # Check frontmatter compliance
context vault templates                        # List available templates
```

**Built-in templates:**
- `default` — 5-folder structure for any project type
- `microservice` — service-focused: API surface, events, dependencies, runbook
- `api-first` — API design, rate limiting, schemas, error formats

### External Data Pull

```bash
context pull github --source owner/repo --type issues
context pull github --source owner/repo --type wiki
context pull openapi --source ./api/openapi.yaml
context pull openapi --source https://petstore3.swagger.io/api/v3/openapi.json
context pull json --source ./package.json
context pull json --source ./pyproject.toml
```

Pulled documents are written to `.contextos/pulled/<connector>/<project>/` and imported with `context import`.

### Plugin Management

```bash
context plugin list                            # List built-in + installed connectors
context plugin install my-confluence-connector # Install from PyPI
```

### CI/CD Integration

```bash
context ci check                               # Validate vault + check stale index (exit 0/1)
context ci index                               # Headless JSON-output index for pipelines
```

### Logs and Observability

```bash
context logs                                   # Show recent app logs
context logs --tail 100                        # Last 100 entries
context logs --type slow                       # Slow queries (>500ms)
context logs --type audit                      # Token usage audit trail
context logs --format json                     # Machine-readable JSON output
```

### Diagnostics

```bash
context doctor                                 # Validate full setup
context doctor --fix                           # Auto-repair common issues (coming in v1.5.1)
context about                                  # Version, architecture, license
context projects                               # All registered projects with index status
```

### Cache Commands

```bash
context cache ls                               # List chunk cache files
context cache clear                            # Clear chunk cache
context cache stats                            # Context response cache hit/miss rate
```

### Export

```bash
context export my-project                      # Export vault as single Markdown file
context export my-project --format json        # Export as JSON
context export my-project --output ./exports/  # Custom output path
```

---

## API Reference

All endpoints on `http://127.0.0.1:8080`. All except `/health` require `Authorization: Bearer ctx_<token>`.

### Core Retrieval

```bash
# Health check (no auth)
GET /health
GET /health?deep=true          # Run live search to verify end-to-end

# Semantic + hybrid search
POST /search
{
  "query": "payment retry backoff",
  "project": "my-project",
  "type": "domain",            # optional filter
  "domain": "payment",         # optional filter
  "limit": 5,
  "include_graph": false,
  "use_hybrid": true,          # BM25 + vector (default)
  "hybrid_alpha": 0.7          # 0=BM25 only, 1=vector only
}

# Assembled context block (main agent endpoint)
POST /context
{
  "query": "implement booking cancellation with refund",
  "project": "my-project",
  "max_tokens": 4000,
  "priority_order": ["context", "adr", "architecture", "domain", "workflow", "product"],
  "use_hybrid": true,
  "hybrid_alpha": 0.7
}

# Response:
{
  "context": "## Current Context\n\n...",
  "sources": [{"title": "...", "type": "...", "filepath": "..."}],
  "token_estimate": 1843
}
```

### Knowledge Graph

```bash
GET /graph                     # Full graph as nodes + edges
GET /documents                 # List indexed documents
GET /documents?type=adr        # Filter by type
GET /documents?domain=payment  # Filter by domain
```

### Session Management

```bash
POST /session/start            # Start session → returns session_id
POST /session/{id}/event       # Log event {type, payload}
POST /session/{id}/end         # End session → returns summary
GET  /session/active           # Get active session
GET  /session/last             # Get last completed session
```

### External Data Pull

```bash
POST /pull?connector=github&source=owner/repo&project=my-project
POST /pull?connector=openapi&source=./openapi.yaml
```

### Observability

```bash
GET /metrics                   # Request stats + cache hit rate (read scope)
GET /audit?limit=50            # Audit log (admin scope)
GET /watcher                   # Watch mode status
```

---

## Agent Integration

### Kiro (Primary Target)

A pre-task hook is included at `.kiro/hooks/contextos-prefetch.json`. It automatically fetches relevant context before every Kiro task.

**Setup:**
```bash
context token create kiro --scope write
export CONTEXTOS_TOKEN=ctx_<your-token>
context serve
```

The hook fires automatically before each task — no manual action required.

### MCP — Universal Agent Integration

ContextOS exposes all retrieval functions as [Model Context Protocol](https://modelcontextprotocol.io) tools. Any MCP-compatible agent gets native tool access with no curl commands.

**Setup (copy `mcp.json.example` to `mcp.json`):**
```json
{
  "mcpServers": {
    "contextos": {
      "command": "context",
      "args": ["mcp"],
      "env": {
        "CONTEXTOS_TOKEN": "ctx_YOUR_TOKEN_HERE"
      }
    }
  }
}
```

**Available MCP tools:**

| Tool | Description | Scope |
|---|---|---|
| `search_knowledge` | Semantic search across vault | read |
| `get_context` | Assembled context block for a task | read |
| `grep_codebase` | Fast regex search across source files | read |
| `read_file` | Read file with optional line range | read |
| `get_graph` | Knowledge graph summary | read |
| `get_status` | Index health check | read |

### Claude Code

Add to `CLAUDE.md` in your project root:

```markdown
## Project Memory

Before starting any task, retrieve context from ContextOS:

```bash
curl -s -X POST http://127.0.0.1:8080/context \
  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "<YOUR TASK HERE>", "project": "<project-name>"}'
```

After completing a task:
```bash
context index    # Update knowledge graph
```
```

### Cursor

`.cursorrules` is auto-generated by `context setup cursor`:

```
context setup cursor
```

Or add manually to `.cursorrules`:

```
Before every task, call ContextOS:
curl -s -X POST http://127.0.0.1:8080/context \
  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \
  -d '{"query": "<task>", "project": "<project>"}'

After completing a task: run `context index`
```

### Continue.dev

```bash
context setup continue
```

Writes `.continue/config.json` with ContextOS as a context provider.

### GitHub Copilot

```bash
context setup copilot
```

Writes `.github/copilot-instructions.md` with pre-task context fetch instructions.

### Cline / Roo / Aider / Any Agent

All agents that respect system prompts or instruction files can use ContextOS. The pattern is always:

1. Check server: `curl http://127.0.0.1:8080/health`
2. Fetch context: `POST /context` with task description
3. Prepend context to system prompt or first message
4. Complete task
5. After task: `context index` to update the graph

```bash
# Generate configs for all agents at once
context setup all
```

### Using ContextOS From Other Project Folders

ContextOS runs as a server — you can query it from any project folder without being in the ContextOS directory:

```bash
# From any project directory
curl -s -X POST http://127.0.0.1:8080/context \
  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "implement booking cancellation", "project": "my-project"}'
```

Keep the server running in the background:
```bash
# In the ContextOS directory
context serve &
# Or with auto-reindex on file changes
context serve --watch &
```

---

## Hybrid Search

ContextOS uses **Hybrid Search (BM25 + Vector + RRF)** for best-in-class retrieval:

```
score = alpha * (1/(k + rank_vector)) + (1-alpha) * (1/(k + rank_bm25))
```

- **alpha = 0.7** (default) — vector-weighted for semantic understanding
- **alpha = 0.0** — pure BM25 keyword search
- **alpha = 1.0** — pure vector semantic search

Hybrid search provides 30-50% better retrieval for exact symbol names, technical terms, and code identifiers compared to vector-only search.

**Configure in `.contextos/config.yaml`:**
```yaml
hybrid_search: true
hybrid_alpha: 0.7
```

**Override per-request:**
```json
POST /search
{
  "query": "BookingService.create_booking",
  "use_hybrid": true,
  "hybrid_alpha": 0.3   // lean toward BM25 for exact matches
}
```

---

## Document Formats

ContextOS indexes more than Markdown:

| Format | Library | Strategy |
|---|---|---|
| `.md` | Native | Full frontmatter + heading chunking |
| `.pdf` | pymupdf | Page-by-page text extraction |
| `.docx` | python-docx | Headings → `#/##/###`, tables → Markdown tables |
| `.pptx` | python-pptx | Slides → `## Slide N: title` + speaker notes |

```bash
# Import a vault containing PDFs and DOCX files
context import ./docs/

# Or pull from external sources
context pull openapi --source ./api/openapi.yaml
context pull github --source owner/repo --type issues
context pull json --source ./package.json
```

---

## Retrieval Evaluation

Measure retrieval quality with the built-in evaluator:

```bash
# Run against the example questions
context eval --questions eval/questions.json.example

# Run against the ContextOS self-test (after context index)
context eval --questions eval/contextos-questions.json

# Compare vector-only vs hybrid
context eval --questions eval/questions.json --no-hybrid   # vector only
context eval --questions eval/questions.json --hybrid      # BM25 + vector

# Save results
context eval --questions eval/questions.json --output eval/results.json
```

**Output:**
```
┌──────────────────────────────────┬───────┐
│ Metric                           │ Score │
├──────────────────────────────────┼───────┤
│ Hit Rate @5                      │ 0.87  │
│ MRR (Mean Reciprocal Rank)       │ 0.74  │
│ Avg top-1 score                  │ 0.82  │
│ No-result queries                │ 0.0%  │
│ Avg latency                      │ 84ms  │
└──────────────────────────────────┴───────┘
```

**Question format** (`eval/questions.json`):
```json
[
  {
    "query": "how does payment retry work",
    "expected_title": "Payment Domain Model",
    "expected_type": "domain",
    "project": "my-project",
    "k": 5
  }
]
```

---

## Plugin System

Extend ContextOS with custom connectors by dropping a Python file into `~/.contextos/plugins/` or `./contextos_plugins/`:

```python
# contextos_plugins/my_confluence.py
from contextos.connectors.base import BaseConnector, ConnectorResult

class ConfluenceConnector(BaseConnector):
    name = "confluence"
    description = "Pull Confluence pages into the vault"

    def fetch(self) -> list[ConnectorResult]:
        space = self.config.get("space", "ENG")
        # ... fetch from Confluence API ...
        return [
            ConnectorResult(
                filename=f"confluence-{page_id}.md",
                content=f"---\nproject: {self.project}\ntype: architecture\n---\n\n{content}",
                title=page_title,
                doc_type="architecture",
            )
        ]
```

```bash
# Plugin auto-discovered from ./contextos_plugins/
context plugin list
# → my_connector (local)    description here

context pull confluence --source my-space --project my-project
```

**Or install from PyPI:**
```bash
context plugin install contextos-confluence-connector
```

Plugins can also be distributed as Python packages with the entry point group `contextos.connectors`.

---

## CI/CD Integration

```yaml
# .github/workflows/contextos-check.yml
name: ContextOS Vault Check

on:
  push:
    paths: ['docs/vault/**']

jobs:
  vault-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e .
      - run: context ci check --vault ./docs/vault
      - run: context ci index
```

```bash
# Local CI check — exits 1 if vault has errors or stale index
context ci check

# Headless index with JSON output
context ci index
# → {"status":"ok","new":2,"changed":1,"unchanged":45,"chunks":180,"elapsed_s":3.2}
```

---

## Configuration

All settings in `.contextos/config.yaml`:

```yaml
project_name: my-project
port: 8080
log_level: info                      # debug | info | warning
embedding_model: BAAI/bge-small-en-v1.5
embedding_dim: 384                   # must match model dimension
hybrid_search: true
hybrid_alpha: 0.7                    # 0.0=BM25 only, 1.0=vector only
vault_paths:
  - /path/to/my-vault
```

**Environment variables** (override config):

```bash
export CONTEXTOS_TOKEN=ctx_<token>    # Bearer token for API
export CONTEXTOS_PORT=8080            # Port override
export CONTEXTOS_LOG_LEVEL=info       # debug | info | warning
```

---

## Architecture Rules

These are non-negotiable constraints enforced in the codebase:

| Rule | Enforcement |
|---|---|
| API binds to `127.0.0.1` only | Hardcoded in `api.py` — never `0.0.0.0` |
| Zero external network calls at runtime | No `requests` to external URLs |
| All paths use `pathlib.Path` | Never `os.path` string concatenation |
| Vault documents are read-only | Indexing never writes to source files |
| Token raw values stored as SHA-256 hash only | Plain text never persisted |
| All Pydantic models in `schema.py` | Single source of truth |
| File access path containment | `context read` validates `is_relative_to()` |

---

## Security Model

- **Localhost-only binding** — API never exposed beyond `127.0.0.1`
- **Bearer token auth** — all endpoints except `/health` require `Authorization: Bearer ctx_<token>`
- **Token scopes** — `read` / `write` / `admin` with hierarchical enforcement
- **Token expiry** — optional TTL: `context token create <name> --expires 30`
- **Rate limiting** — 1000 requests/minute per token, sliding window
- **Token dir permissions** — `chmod 0700` on `.contextos/tokens/` (Unix/macOS)
- **Audit log** — every API call logged to `.contextos/logs/audit.jsonl`
- **Path containment** — `context read` blocks traversal outside vault roots

---

## Performance

| Operation | Performance |
|---|---|
| `context index` (incremental, no changes) | < 1s — hash check, nothing to do |
| `context index` (full, 100 docs) | ~30s (embedding only changed docs) |
| `context search` (warm) | < 100ms P95 |
| `context search` (cold start) | ~2s (model load) |
| `POST /context` (cached) | < 5ms (LRU cache hit) |
| `POST /context` (cache miss) | < 500ms |
| BM25 search (cached index) | < 20ms |
| `context grep` (ripgrep) | < 50ms on any codebase size |

**BM25 cache:** Built at index time, loaded from `.contextos/cache/bm25.pkl` on first query. Eliminates per-query corpus rebuild.

**Incremental index:** Only re-embeds documents whose content hash has changed. Re-indexing 100 unchanged docs completes in under 1 second.

---

## Project Structure

```
contextos/
  schema.py         ← All Pydantic v2 models (single source of truth)
  config.py         ← Runtime configuration
  vault.py          ← Vault scanner + frontmatter parser
  chunker.py        ← Markdown header splitter
  embedder.py       ← sentence-transformers wrapper (BAAI/bge-small)
  store.py          ← LanceDB vector store + hybrid BM25 search
  graph.py          ← NetworkX knowledge graph
  retrieval.py      ← Full retrieval pipeline (filter→hybrid→rerank→assemble)
  auth.py           ← Token generation, scopes, rate limiting
  api.py            ← FastAPI server (127.0.0.1 only)
  cli.py            ← Typer CLI (30 commands)
  ui.py             ← Rich UI theme and shared components
  memory.py         ← Disk management (purge, archive, reset)
  session.py        ← Agent session tracking
  evaluator.py      ← Retrieval quality evaluation
  compressor.py     ← TF-IDF context compression (sumy)
  symbols.py        ← AST symbol index (Python + JS/TS)
  watcher.py        ← Live vault file watcher
  dashboard.py      ← Textual TUI dashboard
  mcp_server.py     ← MCP server (6 native tools)
  logger.py         ← Structured JSON logging
  cache_layer.py    ← LRU context response cache
  plugins.py        ← Plugin discovery and connector registry
  scaffolder.py     ← Vault template scaffolding + validation
  connectors/
    base.py         ← BaseConnector + ConnectorResult
    github.py       ← GitHub Issues + Wiki
    openapi.py      ← OpenAPI/Swagger spec → architecture docs
    json_source.py  ← JSON/YAML/TOML → vault docs
  ingestors/
    pdf.py          ← PDF extraction (pymupdf)
    docx.py         ← Word extraction (python-docx)
    pptx.py         ← PowerPoint extraction (python-pptx)
  templates/
    default/        ← 5-folder vault template
    microservice/   ← Service-focused template
    api-first/      ← API-first template

docs/vault/         ← ContextOS's own knowledge vault (self-documenting)
eval/               ← Retrieval evaluation question sets
tests/              ← 199 tests (smoke, v1.1–v1.5, E2E)
```

---

## Agent Onboarding

See [AGENTS.md](AGENTS.md) for the complete agent rulebook:

- Step-by-step session workflow
- Architecture rules (non-negotiable)
- File dependency order
- API quick reference with JSON shapes
- Environment variable setup
- Memory management commands
- Cross-project usage guide

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development setup
- PR checklist (all architecture rules enforced)
- Commit message format
- Versioning scheme

**Quick contributor setup:**
```bash
git clone https://github.com/AbhayankarBellur/ContextOS.git
cd ContextOS
pip install -e ".[dev]"
context init
context import docs/vault
context index
pytest tests/ -q
```

---

## Roadmap

| Version | Scope |
|---|---|
| **v1.5** (current) | E2E tests, BM25 disk cache, batch delete, configurable embedding dim, watch fix |
| **v1.6** | Cross-encoder re-ranking, semantic deduplication, OCR for scanned PDFs |
| **v2.0** | Optional LAN team sync (no cloud), shared vault over local network |

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**ContextOS** — Built for developers who care about their agents knowing what they're building.

[GitHub](https://github.com/AbhayankarBellur/ContextOS) · [Issues](https://github.com/AbhayankarBellur/ContextOS/issues) · [AGENTS.md](AGENTS.md)

</div>
