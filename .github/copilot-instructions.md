# ContextOS — Project Memory

Before starting any task, call the ContextOS context API:

```bash
curl -s -X POST http://127.0.0.1:8080/context \
  -H 'Authorization: Bearer $CONTEXTOS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"query": "<task>", "project": "<project>"}'
```

See AGENTS.md for full integration guide.
