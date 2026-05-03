# News Notifier — MVP local

Phase 1 du projet (cf. `PROJET_NEWS_NOTIFIER.md`). Script Python qui poll GNews + NewsData.io, dédoublonne par URL via SQLite local, et pousse les nouveaux articles vers ntfy.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # puis remplir les clés
```

### Clés à obtenir
- **GNews** : https://gnews.io (100 req/jour gratuits)
- **NewsData.io** : https://newsdata.io (200 req/jour gratuits)
- **ntfy** : pour tester, choisis un topic aléatoire et difficile à deviner sur `https://ntfy.sh`, ex: `news-notif-XYZ123abc`. Installe l'app ntfy sur ton tel et abonne-toi à ce topic.

`.env` minimal pour démarrer :
```
GNEWS_API_KEY=...
NEWSDATA_API_KEY=...
NTFY_SERVER_URL=https://ntfy.sh
NTFY_TOPIC=news-notif-XYZ123abc
```

## Run

```bash
python main.py
```

Edite les mots-clés dans `config.py` (listes `GNEWS_KEYWORDS` et `NEWSDATA_KEYWORDS`).

## Fichiers

- `main.py` — orchestrateur fetch → dédup → notif
- `sources.py` — clients GNews et NewsData
- `db.py` — dédoublonnage SQLite (TTL 7j)
- `notifier.py` — envoi ntfy
- `config.py` — keywords, langue, limites
- `news.db` — créé au premier run (gitignored)

## Prochaines étapes

- [ ] Tester le pipeline end-to-end (clés réelles + topic ntfy)
- [ ] Choisir/affiner les keywords selon qualité observée
- [ ] Phase 2 : intégrer Claude Haiku pour le scoring
- [ ] Phase 3 : migrer dédup vers Supabase + ntfy self-hosted Render
