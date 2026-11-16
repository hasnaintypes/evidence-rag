# Quick Start

A Supabase project is required regardless of `STORAGE_MODE` — Auth is always Supabase (no
local/mock auth path). Every data route (`/documents`, `/conversations`, `/upload`, `/graph`)
requires a signed-in user.

Every environment variable referenced below is documented in full in
[`CONFIGURATION.md`](./CONFIGURATION.md).

## Server

```bash
cd server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

```env
STORAGE_MODE=local                     # or "supabase" for Postgres+pgvector + Supabase Storage
VOYAGE_API_KEY=your-key-here           # embeddings
LLM_BASE_URL=your-openai-compatible-endpoint  # every active LLM call: final answer, query rewriting,
LLM_API_KEY=your-key-here                     #   reranking, faithfulness judging, conversation titling
LLM_MODEL=your-model-id                       #   (Cloudflare Workers AI, Gemini's own OpenAI-compatible
                                               #   endpoint, a self-hosted server, OpenRouter, etc.)
GEMINI_API_KEY=unused-placeholder      # dormant unless ENABLE_ENTITY_GRAPH=true - any non-empty
                                        #   string works, never sent to Google while it's off
ENABLE_ENTITY_GRAPH=false
SUPABASE_URL=https://your-project.supabase.co
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

If `STORAGE_MODE=supabase`, also set `SUPABASE_DB_URL` (use the **connection pooler** string, port
6543 — the direct host is IPv6-only on many projects) and `SUPABASE_KEY`, and run
`scripts/supabase_schema.sql` once in the Supabase SQL editor.

```bash
python scripts/ingest.py        # indexes docs/fixtures/sample_docs/ as shared documents
uvicorn api.app:app --reload    # http://127.0.0.1:8000/docs for interactive API docs
```

## Web

```bash
cd web
pnpm install
cp .env.example .env
```

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

```bash
pnpm dev
```

Open `http://localhost:3000`, sign up, then start a conversation from the sidebar.
