"""Orchestrateur : fetch → dédup → notif ntfy."""

import logging
import os
import sys

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

    articles: list[sources.Article] = []
    with httpx.Client() as client:
        try:
            articles += sources.fetch_gnews(
                client, gnews_key, config.GNEWS_KEYWORDS,
                config.LANGUAGE, config.MAX_PER_QUERY,
            )
        except httpx.HTTPError as e:
            log.error("GNews fetch failed: %s", e)
        try:
            articles += sources.fetch_newsdata(
                client, newsdata_key, config.NEWSDATA_KEYWORDS,
                config.LANGUAGE, config.MAX_PER_QUERY,
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
            db.purge_old(conn, config.DEDUP_TTL_DAYS)
            for art in articles:
                if not art.url or not art.title:
                    continue
                if db.is_seen(conn, art.url):
                    skipped += 1
                    continue

                try:
                    result = scorer.score_article(ai, art, recent_titles[-5:])
                except Exception as e:
                    log.error("Scoring failed for %s: %s", art.url, e)
                    result = {"score": 5, "priority": "default", "is_duplicate": False, "reason": "scorer error"}

                log.info("Scored [%d] %s — %s", result.get("score", 0), art.title[:60], result.get("reason", ""))

                if result.get("is_duplicate"):
                    log.info("Skipped (semantic dup): %s", art.title[:60])
                    db.mark_seen(conn, art.url)
                    skipped += 1
                    continue

                if result.get("score", 0) < config.MIN_SCORE:
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
                recent_titles.append(art.title)
                sent += 1

        log.info("Done. sent=%d skipped(dup)=%d ignored(low_score)=%d", sent, skipped, ignored)
    return 0


if __name__ == "__main__":
    sys.exit(run())
