"""Envoi de notifications via ntfy (self-host ou ntfy.sh)."""

import httpx


def send(
    client: httpx.Client,
    server_url: str,
    topic: str,
    title: str,
    message: str,
    click_url: str | None = None,
    priority: str = "default",
    auth_token: str | None = None,
    tags: list[str] | None = None,
) -> None:
    payload: dict = {
        "topic": topic,
        "title": title,
        "message": message,
        "priority": _priority_int(priority),
    }
    if click_url:
        payload["click"] = click_url
    if tags:
        payload["tags"] = tags

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    r = client.post(
        server_url.rstrip("/"),
        json=payload,
        headers=headers,
        timeout=10,
    )
    r.raise_for_status()


def _priority_int(priority: str) -> int:
    return {
        "min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5,
    }.get(priority, 3)
