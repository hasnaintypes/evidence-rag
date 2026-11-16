# Security Policy

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for a security vulnerability. Instead:

- Use [GitHub's private vulnerability reporting](../../security/advisories/new) for this repo, or
- Email **mrhasnain.dev@gmail.com** with a description of the issue and steps to reproduce.

This is a solo-maintained project, so response times are best-effort — expect an acknowledgment
within a few days. Please allow time to investigate and ship a fix before any public disclosure.

## Supported Versions

There's no versioned release line — only the `main` branch is maintained. Fixes land there and
deploy from there; there's no backporting to older commits.

## Scope & Current Security Posture

A few things worth knowing before reporting, so a report lands with the right context:

- **Auth**: every route except `/health` and `GET /source/{filename}` requires a Supabase-issued
  JWT, verified against Supabase's public JWKS endpoint (`server/api/deps.py`) — no shared secret
  is stored server-side.
- **Ownership**: per-user ownership is enforced on every document/conversation/graph route via a
  centralized `api/authz.py` — a non-owner gets a 404, not a 403, so existence isn't leaked either.
- **`GET /source/{filename}`** is intentionally unauthenticated (opened via plain browser
  navigation for citation links) but gated by a short-lived signed token instead
  (`server/src/core/security.py`, 10-minute TTL) — see that file and `docs/API.md` before assuming
  this route is simply "open."
- **Untrusted document content**: any signed-in user can upload a document, and its content is
  embedded verbatim into LLM prompts. `server/src/core/guardrails.py`'s
  `scan_for_injection_patterns()` **flags** likely prompt-injection content into telemetry — it does
  **not** block or strip it. Treat this as a partial, iterative defense, not a solved problem
  (tracked as an open concern, not a closed one).
- **Rate limiting** (`server/src/core/rate_limiter.py`) is per-process, in-memory, and
  per-user — it is not a DoS defense across multiple server processes/instances.

If you find a way to read another user's documents/conversations, bypass the source-link token,
get unflagged prompt injection to actually change model behavior in a way that leaks data or
impersonates the system, or anything else in that spirit, that's exactly what this policy is for.
