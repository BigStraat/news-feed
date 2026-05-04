"""Score articles via Gemini Flash and detect semantic duplicates."""

import json
import logging
import re
import time

from google import genai

from sources import Article

log = logging.getLogger("news.scorer")

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 5, 10]

SYSTEM_PROMPT = """\
Tu es un assistant qui évalue la pertinence d'articles d'actualité pour un passionné de tech.

Centres d'intérêt :
- Intelligence artificielle (LLMs, modèles, startups IA, régulation)
- Cybersécurité (failles, attaques, outils, législation)
- Startups tech et levées de fonds
- Développement logiciel et open source

Tu reçois un article (titre + description) et les 5 derniers titres déjà notifiés.

Réponds UNIQUEMENT en JSON valide, sans markdown :
{
  "score": <int 0-10>,
  "priority": "<low|default|high|urgent>",
  "reason": "<courte explication en français>",
  "is_duplicate": <true|false>
}

Règles de scoring :
- 0-3 : hors sujet ou peu intéressant → pas de notification
- 4-5 : intéressant mais pas urgent → priority "low"
- 6-7 : pertinent → priority "default"
- 8-9 : très important → priority "high"
- 10  : breaking news critique → priority "urgent"

Pour is_duplicate : true si l'article couvre essentiellement la même news qu'un des 5 derniers titres (même sujet, même fait, angle différent = duplicate).\
"""


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
