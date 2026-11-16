## What & why

<!-- One or two sentences: what changed, and why. Link an issue if there is one. -->

## Checklist

GitHub Actions is currently billing-locked on this account, so CI (`ruff check`/`ruff format
--check`, the `server/tests/` pytest suite, `pnpm lint`/`pnpm build`) will show as failed or
not-started regardless of this PR's content — that's expected, not a signal to investigate. Run the
equivalent checks locally instead:

- [ ] `server/`: `ruff check .` and `ruff format --check .` pass
- [ ] `server/`: `pytest tests/ -v` passes
- [ ] `web/` (if touched): `pnpm lint` and `pnpm build` pass
- [ ] `/code-review medium` run against this diff, findings addressed or explicitly deferred with a
      reason
- [ ] If this touches a deployed path: Render (server) / Vercel (web) preview or health check
      verified
- [ ] One concern per commit, Conventional Commits style, no `Co-Authored-By`/AI-attribution
      trailers (see `AGENTS.md`)

## Notes for the reviewer

<!-- Anything a reviewer should know: deferred follow-ups, known limitations, manual test steps. -->
