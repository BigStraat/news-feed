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
        raise HTTPException(
            status_code=401, detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
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
    return templates.TemplateResponse(request, "dashboard.html", {
        "active": "dashboard",
        "notifications": notifications, "stats": stats,
    })


# --- Keywords ---

@app.get("/keywords", response_class=HTMLResponse)
def keywords_page(request: Request, conn: sqlite3.Connection = Depends(get_conn),
                  _=Depends(check_auth)):
    keywords = db.get_keywords(conn)
    return templates.TemplateResponse(request, "keywords.html", {
        "active": "keywords", "keywords": keywords,
    })


@app.post("/keywords", response_class=HTMLResponse)
def add_keyword(request: Request, keyword: str = Form(...), source: str = Form(...),
                conn: sqlite3.Connection = Depends(get_conn), _=Depends(check_auth)):
    keyword = keyword.strip()
    if keyword and source in ("gnews", "newsdata"):
        db.add_keyword(conn, keyword, source)
    keywords = db.get_keywords(conn)
    return templates.TemplateResponse(request, "keywords.html", {
        "active": "keywords", "keywords": keywords,
    })


@app.delete("/keywords/{keyword_id}", response_class=HTMLResponse)
def delete_keyword(request: Request, keyword_id: int,
                   conn: sqlite3.Connection = Depends(get_conn), _=Depends(check_auth)):
    db.delete_keyword(conn, keyword_id)
    keywords = db.get_keywords(conn)
    return templates.TemplateResponse(request, "keywords.html", {
        "active": "keywords", "keywords": keywords,
    })


# --- Prompt ---

@app.get("/prompt", response_class=HTMLResponse)
def prompt_page(request: Request, conn: sqlite3.Connection = Depends(get_conn),
                _=Depends(check_auth)):
    prompt = db.get_setting(conn, "prompt") or ""
    return templates.TemplateResponse(request, "prompt.html", {
        "active": "prompt", "prompt": prompt,
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
    return templates.TemplateResponse(request, "settings.html", {
        "active": "settings", "settings": settings,
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
