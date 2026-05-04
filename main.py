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
