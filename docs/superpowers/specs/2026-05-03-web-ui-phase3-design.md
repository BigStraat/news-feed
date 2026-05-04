# Phase 3 — Web UI Design Spec

## Goal

Add a management web UI to the News Notifier so configuration, monitoring, and tuning can happen without redeploying. The UI merges into the existing `news-fetcher` service as a single FastAPI process.

## Architecture

Single FastAPI application replaces `server.py`:

- Serves the UI via Jinja2 templates + HTMX + Tailwind CDN
- Exposes `GET /run` for the external cron trigger (same auth: `X-Cron-Secret` header)
- Exposes `GET /health` for uptime checks
- Basic Auth on all UI routes (`WEBUI_USER` / `WEBUI_PASSWORD` env vars)
- Runs via `uvicorn` (replaces `python server.py` in `render.yaml`)

## Pages

### 1. Dashboard (`/`)

- Table of recent notifications: title (linked), score (badge), priority (colored badge), source origin, timestamp
- Summary cards: notifications today, average score, count per priority level
- Auto-refreshes via HTMX poll (every 60s)

### 2. Keywords (`/keywords`)

- Two-column layout: GNews keywords / NewsData keywords
- Each keyword shown as a pill/tag with a delete button
- Add keyword form per column (HTMX swap, no full reload)
- Visual feedback on add/delete

### 3. Prompt (`/prompt`)

- Textarea pre-filled with current system prompt from DB
- "Save" button (HTMX POST)
- "Reset to default" button restores the hardcoded prompt from `scorer.py`
- Success/error feedback inline

### 4. Settings (`/settings`)

- Language: select dropdown (fr, en, es, de, it, pt)
- Min score threshold: number input (0-10)
- Max articles per query: number input
- Dedup TTL: number input (days)
- Save button (HTMX POST)

## Database Schema (SQLite extension)

Three new tables added alongside the existing `seen_urls`:

```sql
CREATE TABLE IF NOT EXISTS keywords (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword  TEXT NOT NULL,
    source   TEXT NOT NULL CHECK(source IN ('gnews', 'newsdata'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_history (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT NOT NULL,
    url      TEXT NOT NULL,
    source   TEXT NOT NULL,
    score    INTEGER NOT NULL,
    priority TEXT NOT NULL,
    reason   TEXT,
    sent_at  INTEGER NOT NULL
);
```

### Seed logic

On startup, if tables are empty:
- `keywords`: populated from current `config.GNEWS_KEYWORDS` and `config.NEWSDATA_KEYWORDS`
- `settings`: populated with `language=fr`, `min_score=4`, `max_per_query=10`, `dedup_ttl_days=7`, `prompt=<scorer.SYSTEM_PROMPT>`

## Integration with fetcher

`main.py` changes:
- Reads keywords from `keywords` table instead of `config.py` constants
- Reads `min_score`, `language`, `max_per_query`, `dedup_ttl_days` from `settings` table
- Reads scorer prompt from `settings` table (key `prompt`)
- Logs each sent notification to `notification_history`
- `config.py` remains as the source of default values for seeding

## Authentication

- **UI routes**: FastAPI `HTTPBasic` dependency, credentials from `WEBUI_USER` / `WEBUI_PASSWORD` env vars
- **`/run` endpoint**: `X-Cron-Secret` header check (unchanged)
- **`/health` endpoint**: no auth

## Dependencies to add

- `fastapi`
- `uvicorn[standard]`
- `jinja2`
- `python-multipart` (for form handling)

## File structure

```
app.py              # FastAPI app, routes, auth
templates/
  base.html         # Layout: nav, Tailwind CDN, HTMX script
  dashboard.html    # Notification history + stats
  keywords.html     # CRUD keywords
  prompt.html       # Edit scorer prompt
  settings.html     # Edit parameters
```

## Render deployment

- `render.yaml`: update `startCommand` to `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Add `WEBUI_USER` and `WEBUI_PASSWORD` env vars

## Out of scope

- Backup/export config (Phase 4)
- Daily summary mode (Phase 4)
- Supabase migration (not planned)
