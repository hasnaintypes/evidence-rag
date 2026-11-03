# AGENTS.md

Workflow rules for anyone (human or agent) making code changes in this repository.

## Branching & commits

- Never commit directly to `main`. Create a feature branch for every change
  (`fix/...`, `feat/...`, `chore/...`, matching the change's conventional-commit type).
- Commit in small, logical, reviewable units — one concern per commit (e.g. "add the
  security module" and "wire it into the routes" as separate commits, not one giant diff).
  Don't bundle unrelated changes (docs + a feature + a lint cleanup) into a single commit.
- Write commit messages in [Conventional Commits](https://www.conventionalcommits.org/)
  style (`feat(server): ...`, `fix(web): ...`, `docs: ...`, `chore: ...`), with a short
  imperative summary line and, when the "why" isn't obvious from the diff, a body
  explaining it.

## Pull requests

- Open a PR from the feature branch into `main` for every change — don't push straight
  to `main`, even for small fixes.
- Let CI (`.github/workflows/ci.yml` — lint + typecheck; `.github/workflows/eval.yml` —
  retrieval regression gate on retrieval/ingestion changes) finish and go green before
  requesting review. If CI fails, fix the cause before moving on; don't disable or skip
  a check to get around a failure.
- Run the `code-review` skill against the PR before merging. Treat its findings the way
  a human reviewer's comments would be treated: fix what's valid, note what's deferred
  (with a reason), and only merge once the PR is clean or the remaining items are
  explicitly accepted as follow-up work (ideally as a tracked GitHub issue).
- Merge only after CI is green and the review pass is resolved. Prefer squash or a clean
  merge over force-pushing history.

## Tests & CI scope

- CI currently gates on lint (`ruff check`, pyflakes rules only — see `server/pyproject.toml`
  for why the rule set is intentionally narrow for now) and typecheck/build for the web
  app (`pnpm lint` + `pnpm build`, since Next.js App Router's generated types mean
  `next build` is the correct typecheck step, not a bare `tsc --noEmit`).
- There is currently no automated test suite (tracked as its own roadmap item/issue —
  see the repo's GitHub milestones). As tests get added for a given area, wire them into
  `ci.yml` as a blocking step for that area rather than leaving them to run manually.
- When tightening a lint/type rule that would fail on pre-existing code outside your
  change's scope, either fix the pre-existing issues in their own small commit first, or
  scope the new rule narrowly and say so in a comment — don't leave CI red for reasons
  unrelated to the PR at hand.

## Running commands

- Run long-running or blocking commands (CI watch/poll loops, dev servers, builds,
  installs, test suites) in the background rather than foreground, and check back on
  them instead of blocking the whole session on one command. Only run a command in the
  foreground when the very next step genuinely depends on its output and it finishes quickly.

## Documentation

- Project documentation (PRD, architecture, security findings, roadmap, decisions) lives
  in the Obsidian vault, not in this repo — see `CLAUDE.md` for what stays local
  (`README.md`, this file, code-level comments) versus what belongs in the vault.
