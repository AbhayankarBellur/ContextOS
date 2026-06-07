# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.5.x | ✅ Active support |
| 1.4.x | ✅ Security fixes only |
| < 1.4 | ❌ No support |

## Security Model

ContextOS is designed with a security-first local architecture:

- **Localhost-only binding** — API server binds exclusively to `127.0.0.1`. Never `0.0.0.0`.
- **No external network calls at runtime** — zero outbound connections after model download.
- **Token authentication** — Bearer tokens with `read / write / admin` scopes.
- **SHA-256 hash storage** — raw token values are never stored. Hash-only persistence.
- **Rate limiting** — 1000 requests/minute per token, sliding window.
- **Token expiry** — optional TTL on tokens.
- **Path containment** — `context read` validates files are within registered vault roots.
- **Token directory permissions** — `chmod 0700` on `.contextos/tokens/` (Unix/macOS).
- **Audit logging** — every API call logged to `.contextos/logs/audit.jsonl`.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report privately to: **abhayankarbellur@gmail.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within 72 hours and issue a fix within 14 days for confirmed vulnerabilities.

## Known Limitations

- Rate limiting resets on server restart (stored in token file, not shared memory).
- Windows does not enforce `chmod 0700` — token directory is unprotected on Windows.
- The MCP server trusts the `CONTEXTOS_TOKEN` environment variable — set it securely.
- ContextOS is designed for local developer use. Do not expose the API server to a network.
