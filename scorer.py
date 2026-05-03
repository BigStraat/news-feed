"""Score articles via Gemini Flash and detect semantic duplicates."""

import json
import logging

from google import genai

from sources import Article

log = logging.getLogger("news.scorer")

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
) -> dict:
    recent = "\n".join(f"- {t}" for t in recent_titles) if recent_titles else "(aucun)"

    user_msg = (
        f"Article à évaluer :\n"
        f"Titre : {article.title}\n"
        f"Description : {article.description}\n"
        f"Source : {article.source}\n\n"
        f"Derniers titres notifiés :\n{recent}"
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=256,
        ),
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Failed to parse scorer response: %s", text)
        return {"score": 5, "priority": "default", "reason": "parse error", "is_duplicate": False}
