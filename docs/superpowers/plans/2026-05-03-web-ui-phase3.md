# Phase 3 — Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FastAPI web UI with HTMX + Tailwind to manage keywords, prompt, settings, and view notification history — all in the same service that handles the cron `/run` endpoint.

**Architecture:** Single FastAPI app (`app.py`) replaces `server.py`. DB layer (`db.py`) extended with 3 new tables (keywords, settings, notification_history) and seed logic. `main.py` reads config from DB instead of `config.py` constants. Jinja2 templates served with HTMX for interactivity.

**Tech Stack:** Python 3, FastAPI, Jinja2, HTMX, Tailwind CDN, SQLite, uvicorn

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add fastapi, uvicorn, jinja2, python-multipart |
| `db.py` | Modify | Add schema for 3 new tables, seed logic, CRUD functions |
| `app.py` | Create | FastAPI app: routes (UI + /run + /health), auth, templates |
| `templates/base.html` | Create | Layout shell: nav bar, Tailwind CDN, HTMX script tag |
| `templates/dashboard.html` | Create | Notification history table + stat cards |
| `templates/keywords.html` | Create | Two-column keyword CRUD with HTMX |
| `templates/prompt.html` | Create | Textarea for prompt editing |
| `templates/settings.html` | Create | Form for language, min_score, max_per_query, dedup_ttl |
| `main.py` | Modify | Read keywords/settings/prompt from DB, log to notification_history |
| `server.py` | Delete | Replaced by app.py |
| `render.yaml` | Modify | Update startCommand, add WEBUI env vars |

---

## Task 1: Update dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add new dependencies to requirements.txt**

Replace the full file content with:

```
httpx>=0.27
python-dotenv>=1.0
google-genai>=1.0
fastapi>=0.115
uvicorn[standard]>=0.34
jinja2>=3.1
python-multipart>=0.0.18
```

- [ ] **Step 2: Install dependencies**

Run: `.venv\Scripts\pip install -r requirements.txt`

- [ ] **Step 3: Commit**

```
git add requirements.txt
git commit -m "feat: add FastAPI, uvicorn, jinja2, python-multipart dependencies"
```

---

## Task 2: Extend DB schema and add CRUD functions

**Files:**
- Modify: `db.py`

- [ ] **Step 1: Add new table schemas to SCHEMA constant**

In `db.py`, replace the `SCHEMA` constant with:

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_urls (
    url_hash TEXT PRIMARY KEY,
    url      TEXT NOT NULL,
    seen_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seen_at ON seen_urls(seen_at);

CREATE TABLE IF NOT EXISTS keywords (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    source  TEXT NOT NULL CHECK(source IN ('gnews', 'newsdata'))
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
"""
```

- [ ] **Step 2: Add seed function**

Add this function to `db.py` after the existing functions:

```python
def seed_defaults(conn: sqlite3.Connection) -> None:
    """Populate keywords and settings with defaults if tables are empty."""
    import config
    import scorer

    if conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0] == 0:
        for kw in config.GNEWS_KEYWORDS:
            conn.execute(
                "INSERT INTO keywords (keyword, source) VALUES (?, ?)",
                (kw, "gnews"),
            )
        for kw in config.NEWSDATA_KEYWORDS:
            conn.execute(
                "INSERT INTO keywords (keyword, source) VALUES (?, ?)",
                (kw, "newsdata"),
            )

    if conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        defaults = {
            "language": config.LANGUAGE,
            "min_score": str(config.MIN_SCORE),
            "max_per_query": str(config.MAX_PER_QUERY),
            "dedup_ttl_days": str(config.DEDUP_TTL_DAYS),
            "prompt": scorer.SYSTEM_PROMPT,
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)", (k, v),
            )
```

- [ ] **Step 3: Add keyword CRUD functions**

Add to `db.py`:

```python
def get_keywords(conn: sqlite3.Connection, source: str | None = None) -> list[dict]:
    if source:
        rows = conn.execute(
            "SELECT id, keyword, source FROM keywords WHERE source = ? ORDER BY id",
            (source,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, keyword, source FROM keywords ORDER BY id",
        ).fetchall()
    return [{"id": r[0], "keyword": r[1], "source": r[2]} for r in rows]


def add_keyword(conn: sqlite3.Connection, keyword: str, source: str) -> None:
    conn.execute(
        "INSERT INTO keywords (keyword, source) VALUES (?, ?)", (keyword, source),
    )
    conn.commit()


def delete_keyword(conn: sqlite3.Connection, keyword_id: int) -> None:
    conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
    conn.commit()
```

- [ ] **Step 4: Add settings get/set functions**

Add to `db.py`:

```python
def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,),
    ).fetchone()
    return row[0] if row else None


def get_all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r[0]: r[1] for r in rows}


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value),
    )
    conn.commit()
```

- [ ] **Step 5: Add notification history functions**

Add to `db.py`:

```python
def log_notification(
    conn: sqlite3.Connection,
    title: str,
    url: str,
    source: str,
    score: int,
    priority: str,
    reason: str | None,
) -> None:
    conn.execute(
        "INSERT INTO notification_history (title, url, source, score, priority, reason, sent_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, url, source, score, priority, reason, int(time.time())),
    )
    conn.commit()


def get_recent_notifications(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, url, source, score, priority, reason, sent_at "
        "FROM notification_history ORDER BY sent_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r[0], "title": r[1], "url": r[2], "source": r[3],
            "score": r[4], "priority": r[5], "reason": r[6], "sent_at": r[7],
        }
        for r in rows
    ]


def get_notification_stats(conn: sqlite3.Connection) -> dict:
    today_start = int(time.time()) - (int(time.time()) % 86400)
    today_count = conn.execute(
        "SELECT COUNT(*) FROM notification_history WHERE sent_at >= ?",
        (today_start,),
    ).fetchone()[0]
    avg_score = conn.execute(
        "SELECT AVG(score) FROM notification_history WHERE sent_at >= ?",
        (today_start,),
    ).fetchone()[0]
    priority_counts = conn.execute(
        "SELECT priority, COUNT(*) FROM notification_history "
        "WHERE sent_at >= ? GROUP BY priority",
        (today_start,),
    ).fetchall()
    return {
        "today_count": today_count,
        "avg_score": round(avg_score, 1) if avg_score else 0,
        "by_priority": {r[0]: r[1] for r in priority_counts},
    }
```

- [ ] **Step 6: Commit**

```
git add db.py
git commit -m "feat: extend DB with keywords, settings, notification_history tables"
```

---

## Task 3: Create base template

**Files:**
- Create: `templates/base.html`

- [ ] **Step 1: Create templates directory**

Run: `mkdir templates` (if it doesn't exist)

- [ ] **Step 2: Create base.html**

Create `templates/base.html`:

```html
<!DOCTYPE html>
<html lang="fr" class="h-full bg-gray-50">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}News Notifier{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body class="h-full">
    <div class="min-h-full">
        <nav class="bg-gray-800">
            <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                <div class="flex h-16 items-center justify-between">
                    <div class="flex items-center">
                        <span class="text-white font-bold text-lg">News Notifier</span>
                        <div class="ml-10 flex items-baseline space-x-4">
                            <a href="/" class="rounded-md px-3 py-2 text-sm font-medium {% if active == 'dashboard' %}bg-gray-900 text-white{% else %}text-gray-300 hover:bg-gray-700 hover:text-white{% endif %}">Dashboard</a>
                            <a href="/keywords" class="rounded-md px-3 py-2 text-sm font-medium {% if active == 'keywords' %}bg-gray-900 text-white{% else %}text-gray-300 hover:bg-gray-700 hover:text-white{% endif %}">Keywords</a>
                            <a href="/prompt" class="rounded-md px-3 py-2 text-sm font-medium {% if active == 'prompt' %}bg-gray-900 text-white{% else %}text-gray-300 hover:bg-gray-700 hover:text-white{% endif %}">Prompt</a>
                            <a href="/settings" class="rounded-md px-3 py-2 text-sm font-medium {% if active == 'settings' %}bg-gray-900 text-white{% else %}text-gray-300 hover:bg-gray-700 hover:text-white{% endif %}">Settings</a>
                        </div>
                    </div>
                </div>
            </div>
        </nav>
        <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            {% block content %}{% endblock %}
        </main>
    </div>
</body>
</html>
```

- [ ] **Step 3: Commit**

```
git add templates/base.html
git commit -m "feat: add base HTML template with nav and Tailwind/HTMX"
```

---

## Task 4: Create dashboard template

**Files:**
- Create: `templates/dashboard.html`

- [ ] **Step 1: Create dashboard.html**

Create `templates/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}Dashboard — News Notifier{% endblock %}
{% block content %}
<div class="mb-6">
    <h1 class="text-2xl font-bold text-gray-900">Dashboard</h1>
</div>

<!-- Stats cards -->
<div class="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-8">
    <div class="bg-white overflow-hidden shadow rounded-lg p-5">
        <div class="text-sm font-medium text-gray-500 truncate">Notifications aujourd'hui</div>
        <div class="mt-1 text-3xl font-semibold text-gray-900">{{ stats.today_count }}</div>
    </div>
    <div class="bg-white overflow-hidden shadow rounded-lg p-5">
        <div class="text-sm font-medium text-gray-500 truncate">Score moyen</div>
        <div class="mt-1 text-3xl font-semibold text-gray-900">{{ stats.avg_score }}</div>
    </div>
    <div class="bg-white overflow-hidden shadow rounded-lg p-5">
        <div class="text-sm font-medium text-gray-500 truncate">Par priorité</div>
        <div class="mt-2 flex flex-wrap gap-2">
            {% for p, count in stats.by_priority.items() %}
            <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium
                {% if p == 'urgent' %}bg-red-100 text-red-800
                {% elif p == 'high' %}bg-orange-100 text-orange-800
                {% elif p == 'default' %}bg-blue-100 text-blue-800
                {% else %}bg-gray-100 text-gray-800{% endif %}">
                {{ p }}: {{ count }}
            </span>
            {% endfor %}
            {% if not stats.by_priority %}
            <span class="text-gray-400 text-sm">—</span>
            {% endif %}
        </div>
    </div>
</div>

<!-- Notification history -->
<div class="bg-white shadow rounded-lg" hx-get="/" hx-trigger="every 60s" hx-select="#notif-table" hx-target="#notif-table" hx-swap="outerHTML">
    <div class="px-4 py-5 sm:px-6 border-b border-gray-200">
        <h2 class="text-lg font-medium text-gray-900">Dernières notifications</h2>
    </div>
    <div id="notif-table" class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
                <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Titre</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Priorité</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Raison</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
                {% for n in notifications %}
                <tr>
                    <td class="px-6 py-4 text-sm">
                        <a href="{{ n.url }}" target="_blank" class="text-indigo-600 hover:text-indigo-900 hover:underline">{{ n.title[:80] }}{% if n.title|length > 80 %}...{% endif %}</a>
                    </td>
                    <td class="px-6 py-4">
                        <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold
                            {% if n.score >= 8 %}bg-green-100 text-green-800
                            {% elif n.score >= 6 %}bg-blue-100 text-blue-800
                            {% else %}bg-gray-100 text-gray-800{% endif %}">
                            {{ n.score }}
                        </span>
                    </td>
                    <td class="px-6 py-4">
                        <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium
                            {% if n.priority == 'urgent' %}bg-red-100 text-red-800
                            {% elif n.priority == 'high' %}bg-orange-100 text-orange-800
                            {% elif n.priority == 'default' %}bg-blue-100 text-blue-800
                            {% else %}bg-gray-100 text-gray-800{% endif %}">
                            {{ n.priority }}
                        </span>
                    </td>
                    <td class="px-6 py-4 text-sm text-gray-500">{{ n.source }}</td>
                    <td class="px-6 py-4 text-sm text-gray-500">{{ n.reason[:60] if n.reason else '—' }}</td>
                    <td class="px-6 py-4 text-sm text-gray-500 whitespace-nowrap">{{ n.sent_at_fmt }}</td>
                </tr>
                {% endfor %}
                {% if not notifications %}
                <tr>
                    <td colspan="6" class="px-6 py-8 text-center text-gray-400">Aucune notification envoyée</td>
                </tr>
                {% endif %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```
git add templates/dashboard.html
git commit -m "feat: add dashboard template with stats and notification table"
```

---

## Task 5: Create keywords template

**Files:**
- Create: `templates/keywords.html`

- [ ] **Step 1: Create keywords.html**

Create `templates/keywords.html`:

```html
{% extends "base.html" %}
{% block title %}Keywords — News Notifier{% endblock %}
{% block content %}
<div class="mb-6">
    <h1 class="text-2xl font-bold text-gray-900">Keywords</h1>
    <p class="mt-1 text-sm text-gray-500">Mots-clés utilisés pour rechercher des articles sur chaque API.</p>
</div>

<div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    {% for source, label in [("gnews", "GNews"), ("newsdata", "NewsData")] %}
    <div class="bg-white shadow rounded-lg p-6">
        <h2 class="text-lg font-medium text-gray-900 mb-4">{{ label }}</h2>

        <div id="{{ source }}-list" class="flex flex-wrap gap-2 mb-4">
            {% for kw in keywords if kw.source == source %}
            <span class="inline-flex items-center gap-x-1 rounded-full bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700">
                {{ kw.keyword }}
                <button
                    hx-delete="/keywords/{{ kw.id }}"
                    hx-target="#keyword-page"
                    hx-swap="innerHTML"
                    class="ml-1 text-indigo-400 hover:text-indigo-600 cursor-pointer">&times;</button>
            </span>
            {% endfor %}
            {% if not keywords|selectattr("source", "equalto", source)|list %}
            <span class="text-gray-400 text-sm">Aucun keyword</span>
            {% endif %}
        </div>

        <form hx-post="/keywords" hx-target="#keyword-page" hx-swap="innerHTML" class="flex gap-2">
            <input type="hidden" name="source" value="{{ source }}">
            <input type="text" name="keyword" required placeholder="Nouveau keyword..."
                   class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm px-3 py-2 border">
            <button type="submit"
                    class="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500">
                Ajouter
            </button>
        </form>
    </div>
    {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```
git add templates/keywords.html
git commit -m "feat: add keywords template with HTMX CRUD"
```

---

## Task 6: Create prompt template

**Files:**
- Create: `templates/prompt.html`

- [ ] **Step 1: Create prompt.html**

Create `templates/prompt.html`:

```html
{% extends "base.html" %}
{% block title %}Prompt — News Notifier{% endblock %}
{% block content %}
<div class="mb-6">
    <h1 class="text-2xl font-bold text-gray-900">Prompt LLM</h1>
    <p class="mt-1 text-sm text-gray-500">Prompt système envoyé à Gemini Flash pour le scoring des articles.</p>
</div>

<div class="bg-white shadow rounded-lg p-6">
    <form hx-post="/prompt" hx-target="#prompt-feedback" hx-swap="innerHTML">
        <textarea name="prompt" rows="20"
                  class="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm font-mono p-3 border">{{ prompt }}</textarea>
        <div class="mt-4 flex items-center gap-4">
            <button type="submit"
                    class="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500">
                Sauvegarder
            </button>
            <button type="button"
                    hx-post="/prompt/reset"
                    hx-target="#prompt-feedback"
                    hx-swap="innerHTML"
                    class="rounded-md bg-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 shadow-sm hover:bg-gray-300">
                Réinitialiser par défaut
            </button>
            <div id="prompt-feedback"></div>
        </div>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```
git add templates/prompt.html
git commit -m "feat: add prompt editing template"
```

---

## Task 7: Create settings template

**Files:**
- Create: `templates/settings.html`

- [ ] **Step 1: Create settings.html**

Create `templates/settings.html`:

```html
{% extends "base.html" %}
{% block title %}Paramètres — News Notifier{% endblock %}
{% block content %}
<div class="mb-6">
    <h1 class="text-2xl font-bold text-gray-900">Paramètres</h1>
</div>

<div class="bg-white shadow rounded-lg p-6 max-w-2xl">
    <form hx-post="/settings" hx-target="#settings-feedback" hx-swap="innerHTML">
        <div class="space-y-6">
            <div>
                <label for="language" class="block text-sm font-medium text-gray-700">Langue</label>
                <select id="language" name="language"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm border px-3 py-2">
                    {% for code, label in [("fr", "Français"), ("en", "English"), ("es", "Español"), ("de", "Deutsch"), ("it", "Italiano"), ("pt", "Português")] %}
                    <option value="{{ code }}" {% if settings.language == code %}selected{% endif %}>{{ label }}</option>
                    {% endfor %}
                </select>
            </div>
            <div>
                <label for="min_score" class="block text-sm font-medium text-gray-700">Score minimum (0-10)</label>
                <input type="number" id="min_score" name="min_score" min="0" max="10"
                       value="{{ settings.min_score }}"
                       class="mt-1 block w-32 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm border px-3 py-2">
                <p class="mt-1 text-xs text-gray-500">Les articles en dessous de ce score ne déclenchent pas de notification.</p>
            </div>
            <div>
                <label for="max_per_query" class="block text-sm font-medium text-gray-700">Max articles par requête</label>
                <input type="number" id="max_per_query" name="max_per_query" min="1" max="50"
                       value="{{ settings.max_per_query }}"
                       class="mt-1 block w-32 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm border px-3 py-2">
            </div>
            <div>
                <label for="dedup_ttl_days" class="block text-sm font-medium text-gray-700">TTL dédoublonnage (jours)</label>
                <input type="number" id="dedup_ttl_days" name="dedup_ttl_days" min="1" max="30"
                       value="{{ settings.dedup_ttl_days }}"
                       class="mt-1 block w-32 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm border px-3 py-2">
            </div>
        </div>
        <div class="mt-6 flex items-center gap-4">
            <button type="submit"
                    class="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500">
                Sauvegarder
            </button>
            <div id="settings-feedback"></div>
        </div>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```
git add templates/settings.html
git commit -m "feat: add settings template"
```

---

## Task 8: Create FastAPI app with all routes

**Files:**
- Create: `app.py`

- [ ] **Step 1: Create app.py**

Create `app.py` with the full FastAPI application:

```python
"""FastAPI app — serves the web UI and the /run cron endpoint."""

import os
import secrets
import sqlite3
import sys
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

load_dotenv()

import db

app = FastAPI(docs_url=None, redoc_url=None)
security = HTTPBasic()
templates = Jinja2Templates(directory="templates")

DB_PATH = os.getenv("DB_PATH", "news.db")
CRON_SECRET = os.getenv("CRON_SECRET", "")
WEBUI_USER = os.getenv("WEBUI_USER", "admin")
WEBUI_PASSWORD = os.getenv("WEBUI_PASSWORD", "")


def _init_db() -> None:
    with db.connect(DB_PATH) as conn:
        db.seed_defaults(conn)


_init_db()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(db.SCHEMA)
    try:
        yield conn
    finally:
        conn.close()


def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not WEBUI_PASSWORD:
        return credentials
    correct_user = secrets.compare_digest(credentials.username, WEBUI_USER)
    correct_pass = secrets.compare_digest(credentials.password, WEBUI_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Unauthorized",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials


def _ts_to_str(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m %H:%M")


# --- Health / Cron (no auth) ---

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


@app.get("/run", response_class=PlainTextResponse)
def run_fetch(request: Request):
    cron_secret = request.headers.get("X-Cron-Secret", "")
    if CRON_SECRET and cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="unauthorized")
    threading.Thread(target=_trigger_run, daemon=True).start()
    return "started"


def _trigger_run():
    import main
    try:
        main.run()
    except Exception as e:
        print(f"Run failed: {e}", file=sys.stderr)


# --- Dashboard ---

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, conn: sqlite3.Connection = Depends(get_conn),
              _=Depends(check_auth)):
    notifications = db.get_recent_notifications(conn)
    for n in notifications:
        n["sent_at_fmt"] = _ts_to_str(n["sent_at"])
    stats = db.get_notification_stats(conn)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "active": "dashboard",
        "notifications": notifications, "stats": stats,
    })


# --- Keywords ---

@app.get("/keywords", response_class=HTMLResponse)
def keywords_page(request: Request, conn: sqlite3.Connection = Depends(get_conn),
                  _=Depends(check_auth)):
    keywords = db.get_keywords(conn)
    return templates.TemplateResponse("keywords.html", {
        "request": request, "active": "keywords", "keywords": keywords,
    })


@app.post("/keywords", response_class=HTMLResponse)
def add_keyword(request: Request, keyword: str = Form(...), source: str = Form(...),
                conn: sqlite3.Connection = Depends(get_conn), _=Depends(check_auth)):
    keyword = keyword.strip()
    if keyword and source in ("gnews", "newsdata"):
        db.add_keyword(conn, keyword, source)
    keywords = db.get_keywords(conn)
    return templates.TemplateResponse("keywords.html", {
        "request": request, "active": "keywords", "keywords": keywords,
    })


@app.delete("/keywords/{keyword_id}", response_class=HTMLResponse)
def delete_keyword(request: Request, keyword_id: int,
                   conn: sqlite3.Connection = Depends(get_conn), _=Depends(check_auth)):
    db.delete_keyword(conn, keyword_id)
    keywords = db.get_keywords(conn)
    return templates.TemplateResponse("keywords.html", {
        "request": request, "active": "keywords", "keywords": keywords,
    })


# --- Prompt ---

@app.get("/prompt", response_class=HTMLResponse)
def prompt_page(request: Request, conn: sqlite3.Connection = Depends(get_conn),
                _=Depends(check_auth)):
    prompt = db.get_setting(conn, "prompt") or ""
    return templates.TemplateResponse("prompt.html", {
        "request": request, "active": "prompt", "prompt": prompt,
    })


@app.post("/prompt", response_class=HTMLResponse)
def save_prompt(request: Request, prompt: str = Form(...),
                conn: sqlite3.Connection = Depends(get_conn), _=Depends(check_auth)):
    db.set_setting(conn, "prompt", prompt.strip())
    return HTMLResponse('<span class="text-green-600 text-sm font-medium">Sauvegardé</span>')


@app.post("/prompt/reset", response_class=HTMLResponse)
def reset_prompt(conn: sqlite3.Connection = Depends(get_conn), _=Depends(check_auth)):
    import scorer
    db.set_setting(conn, "prompt", scorer.SYSTEM_PROMPT)
    return HTMLResponse('<span class="text-green-600 text-sm font-medium">Prompt réinitialisé — rechargez la page</span>')


# --- Settings ---

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, conn: sqlite3.Connection = Depends(get_conn),
                  _=Depends(check_auth)):
    settings = db.get_all_settings(conn)
    return templates.TemplateResponse("settings.html", {
        "request": request, "active": "settings", "settings": settings,
    })


@app.post("/settings", response_class=HTMLResponse)
def save_settings(
    language: str = Form(...),
    min_score: str = Form(...),
    max_per_query: str = Form(...),
    dedup_ttl_days: str = Form(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _=Depends(check_auth),
):
    db.set_setting(conn, "language", language)
    db.set_setting(conn, "min_score", min_score)
    db.set_setting(conn, "max_per_query", max_per_query)
    db.set_setting(conn, "dedup_ttl_days", dedup_ttl_days)
    return HTMLResponse('<span class="text-green-600 text-sm font-medium">Sauvegardé</span>')
```

- [ ] **Step 2: Commit**

```
git add app.py
git commit -m "feat: add FastAPI app with all UI routes, auth, and cron endpoint"
```

---

## Task 9: Update main.py to use DB config and log notifications

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Rewrite main.py to read from DB**

Replace the full content of `main.py` with:

```python
"""Orchestrateur : fetch → dédup → score → notif ntfy."""

import logging
import os
import sys
import time

import httpx
from dotenv import load_dotenv
from google import genai

import config
import db
import notifier
import scorer
import sources


def setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        print(f"ERREUR: variable d'environnement manquante: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def run() -> int:
    load_dotenv()
    setup_logging()
    log = logging.getLogger("news")

    gnews_key = require_env("GNEWS_API_KEY")
    newsdata_key = require_env("NEWSDATA_API_KEY")
    gemini_key = require_env("GEMINI_API_KEY")
    ntfy_url = require_env("NTFY_SERVER_URL")
    ntfy_topic = require_env("NTFY_TOPIC")
    ntfy_token = os.getenv("NTFY_AUTH_TOKEN") or None
    db_path = os.getenv("DB_PATH", "news.db")

    with db.connect(db_path) as conn:
        db.seed_defaults(conn)

        settings = db.get_all_settings(conn)
        language = settings.get("language", config.LANGUAGE)
        min_score = int(settings.get("min_score", str(config.MIN_SCORE)))
        max_per_query = int(settings.get("max_per_query", str(config.MAX_PER_QUERY)))
        dedup_ttl_days = int(settings.get("dedup_ttl_days", str(config.DEDUP_TTL_DAYS)))
        prompt = settings.get("prompt", scorer.SYSTEM_PROMPT)

        gnews_kws = [k["keyword"] for k in db.get_keywords(conn, "gnews")]
        newsdata_kws = [k["keyword"] for k in db.get_keywords(conn, "newsdata")]

        if not gnews_kws:
            gnews_kws = config.GNEWS_KEYWORDS
        if not newsdata_kws:
            newsdata_kws = config.NEWSDATA_KEYWORDS

    articles: list[sources.Article] = []
    with httpx.Client() as client:
        try:
            articles += sources.fetch_gnews(
                client, gnews_key, gnews_kws, language, max_per_query,
            )
        except httpx.HTTPError as e:
            log.error("GNews fetch failed: %s", e)
        try:
            articles += sources.fetch_newsdata(
                client, newsdata_key, newsdata_kws, language, max_per_query,
            )
        except httpx.HTTPError as e:
            log.error("NewsData fetch failed: %s", e)

        log.info("Fetched %d articles total", len(articles))

        ai = genai.Client(api_key=gemini_key)
        sent = 0
        skipped = 0
        ignored = 0
        recent_titles: list[str] = []

        with db.connect(db_path) as conn:
            db.purge_old(conn, dedup_ttl_days)
            for art in articles:
                if not art.url or not art.title:
                    continue
                if db.is_seen(conn, art.url):
                    skipped += 1
                    continue

                time.sleep(4)
                try:
                    result = scorer.score_article(ai, art, recent_titles[-5:], prompt)
                except Exception as e:
                    log.error("Scoring failed for %s: %s", art.url, e)
                    result = {"score": 5, "priority": "default", "is_duplicate": False, "reason": "scorer error"}

                log.info("Scored [%d] %s — %s", result.get("score", 0), art.title[:60], result.get("reason", ""))

                if result.get("is_duplicate"):
                    log.info("Skipped (semantic dup): %s", art.title[:60])
                    db.mark_seen(conn, art.url)
                    skipped += 1
                    continue

                if result.get("score", 0) < min_score:
                    db.mark_seen(conn, art.url)
                    ignored += 1
                    continue

                try:
                    notifier.send(
                        client,
                        server_url=ntfy_url,
                        topic=ntfy_topic,
                        title=art.title,
                        message=result.get("reason", art.description or art.source),
                        click_url=art.url,
                        priority=result.get("priority", "default"),
                        auth_token=ntfy_token,
                        tags=[art.origin],
                    )
                except httpx.HTTPError as e:
                    log.error("ntfy send failed for %s: %s", art.url, e)
                    continue

                db.mark_seen(conn, art.url)
                db.log_notification(
                    conn,
                    title=art.title,
                    url=art.url,
                    source=art.origin,
                    score=result.get("score", 0),
                    priority=result.get("priority", "default"),
                    reason=result.get("reason"),
                )
                recent_titles.append(art.title)
                sent += 1

        log.info("Done. sent=%d skipped(dup)=%d ignored(low_score)=%d", sent, skipped, ignored)
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 2: Commit**

```
git add main.py
git commit -m "feat: main.py reads config from DB, logs notifications to history"
```

---

## Task 10: Update scorer.py to accept prompt parameter

**Files:**
- Modify: `scorer.py`

- [ ] **Step 1: Add prompt parameter to score_article**

In `scorer.py`, change the `score_article` function signature and body. Replace the function (lines 47-95) with:

```python
def score_article(
    client: genai.Client,
    article: Article,
    recent_titles: list[str],
    prompt: str | None = None,
) -> dict:
    system_prompt = prompt or SYSTEM_PROMPT
    recent = "\n".join(f"- {t}" for t in recent_titles) if recent_titles else "(aucun)"

    user_msg = (
        f"Article à évaluer :\n"
        f"Titre : {article.title}\n"
        f"Description : {article.description}\n"
        f"Source : {article.source}\n\n"
        f"Derniers titres notifiés :\n{recent}"
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_msg,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=256,
                    thinking_config=genai.types.ThinkingConfig(thinking_budget=0),
                ),
            )
            break
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(e, "code", None)
            if status in (429, 503) and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                log.warning("Gemini %s, retry in %ds (%d/%d)", status, wait, attempt + 1, MAX_RETRIES)
                time.sleep(wait)
            else:
                raise

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    log.warning("Failed to parse scorer response: %s", text)
    return {"score": 5, "priority": "default", "reason": "parse error", "is_duplicate": False}
```

- [ ] **Step 2: Commit**

```
git add scorer.py
git commit -m "feat: scorer accepts optional prompt parameter from DB"
```

---

## Task 11: Delete server.py and update render.yaml

**Files:**
- Delete: `server.py`
- Modify: `render.yaml`

- [ ] **Step 1: Delete server.py**

Run: `git rm server.py`

- [ ] **Step 2: Update render.yaml**

Replace the full content of `render.yaml` with:

```yaml
services:
  # ntfy self-hosted — push notification server
  - type: web
    name: ntfy-server
    runtime: docker
    dockerfilePath: ./Dockerfile.ntfy
    plan: free
    envVars:
      - key: NTFY_BASE_URL
        sync: false
      - key: NTFY_AUTH_DEFAULT_ACCESS
        value: deny-all

  # news-fetcher + web UI — single FastAPI service
  - type: web
    name: news-fetcher
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app:app --host 0.0.0.0 --port $PORT
    plan: free
    envVars:
      - key: GNEWS_API_KEY
        sync: false
      - key: NEWSDATA_API_KEY
        sync: false
      - key: GEMINI_API_KEY
        sync: false
      - key: NTFY_SERVER_URL
        sync: false
      - key: NTFY_TOPIC
        sync: false
      - key: NTFY_AUTH_TOKEN
        sync: false
      - key: CRON_SECRET
        sync: false
      - key: WEBUI_USER
        sync: false
      - key: WEBUI_PASSWORD
        sync: false
      - key: DB_PATH
        value: /tmp/news.db
```

- [ ] **Step 3: Commit**

```
git add render.yaml
git commit -m "feat: replace server.py with FastAPI app, update render.yaml"
```

---

## Task 12: Test locally

- [ ] **Step 1: Start the server**

Run: `.venv\Scripts\python -m uvicorn app:app --reload --port 8000`

- [ ] **Step 2: Verify all pages load**

Open in browser:
- `http://localhost:8000/` — Dashboard (should show empty table + stats)
- `http://localhost:8000/keywords` — Keywords (should show seeded defaults)
- `http://localhost:8000/prompt` — Prompt (should show the default scorer prompt)
- `http://localhost:8000/settings` — Settings (should show fr, 4, 10, 7)
- `http://localhost:8000/health` — Should return "ok" without auth

- [ ] **Step 3: Test CRUD operations**

- Add a keyword on the keywords page → pill appears
- Delete a keyword → pill disappears
- Edit prompt → save → "Sauvegardé" confirmation
- Change a setting → save → "Sauvegardé" confirmation

- [ ] **Step 4: Test cron endpoint**

Run: `curl http://localhost:8000/run` (should return "started" or 401 if CRON_SECRET is set)

- [ ] **Step 5: Final commit**

```
git add -A
git commit -m "feat: Phase 3 complete — Web UI with dashboard, keywords, prompt, settings"
```
