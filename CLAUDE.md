# ContextOS Project Memory

This project uses ContextOS itself for persistent knowledge management.

## Before Starting Any Task

Retrieve context from the local ContextOS server:

```bash
curl -s -X POST http://127.0.0.1:8765/context \
  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "<YOUR TASK HERE>", "project": "contextos", "max_tokens": 4000}'
```

If server is not running:
```bash
cd /path/to/contextos && context serve --port 8765 &
```

## Architecture Rules
See AGENTS.md for complete rules. Critical constraints:
- API server MUST bind to 127.0.0.1 only (never 0.0.0.0)
- No external network calls at runtime
- All paths use pathlib.Path
- Vault documents are read-only
- Token raw values are never stored — SHA-256 hash only
- All Pydantic models live in schema.py

## After Task Completion
```bash
context index    # update knowledge graph
context status   # verify
```
