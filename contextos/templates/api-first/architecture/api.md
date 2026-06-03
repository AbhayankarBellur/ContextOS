---
project: {{project_name}}
type: architecture
domain: api
status: draft
owner: {{team}}
updated_at: {{date}}
tags:
  - api
  - architecture
---

# {{project_name}} API Design

## Design Principles

- RESTful resource naming
- Consistent error format: `{error, message, request_id}`
- Versioning strategy: URL prefix `/v1/`
- Authentication: Bearer token

## Base URL

`https://api.{{project_name}}.example.com/v1`

## Common Headers

| Header | Required | Description |
|---|---|---|
| `Authorization` | Yes | Bearer token |
| `Content-Type` | POST/PUT | `application/json` |
| `X-Request-ID` | No | Client-supplied trace ID |

## Error Format

```json
{
  "error": "NOT_FOUND",
  "message": "Resource not found",
  "request_id": "req_abc123"
}
```

## Rate Limiting

- 1000 requests/minute per token
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
