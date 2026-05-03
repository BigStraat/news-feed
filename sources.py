"""Récupération d'articles depuis GNews et NewsData.io."""

from dataclasses import dataclass
from typing import Iterable

import httpx

GNEWS_URL = "https://gnews.io/api/v4/search"
NEWSDATA_URL = "https://newsdata.io/api/1/news"


@dataclass(frozen=True)
class Article:
    title: str
    description: str
    url: str
    source: str
    published_at: str
    origin: str  # "gnews" | "newsdata"


def fetch_gnews(
    client: httpx.Client,
    api_key: str,
    keywords: Iterable[str],
    language: str,
    max_per_query: int,
) -> list[Article]:
    out: list[Article] = []
    for kw in keywords:
        r = client.get(
            GNEWS_URL,
            params={
                "q": kw,
                "lang": language,
                "max": max_per_query,
                "apikey": api_key,
            },
            timeout=15,
        )
        r.raise_for_status()
        for a in r.json().get("articles", []):
            out.append(
                Article(
                    title=a.get("title") or "",
                    description=a.get("description") or "",
                    url=a.get("url") or "",
                    source=(a.get("source") or {}).get("name") or "",
                    published_at=a.get("publishedAt") or "",
                    origin="gnews",
                )
            )
    return out


def fetch_newsdata(
    client: httpx.Client,
    api_key: str,
    keywords: Iterable[str],
    language: str,
    max_per_query: int,
) -> list[Article]:
    out: list[Article] = []
    for kw in keywords:
        r = client.get(
            NEWSDATA_URL,
            params={
                "apikey": api_key,
                "q": kw,
                "language": language,
                "size": max_per_query,
            },
            timeout=15,
        )
        r.raise_for_status()
        for a in r.json().get("results", []):
            out.append(
                Article(
                    title=a.get("title") or "",
                    description=a.get("description") or "",
                    url=a.get("link") or "",
                    source=a.get("source_id") or "",
                    published_at=a.get("pubDate") or "",
                    origin="newsdata",
                )
            )
    return out
