# TODO — News Notifier

## Phase 1 — MVP ✅
- [x] Script Python qui poll GNews + NewsData
- [x] Dédoublonnage par URL (SQLite)
- [x] Envoi de notifications via ntfy
- [x] Déploiement sur Render (2 web services free)
- [x] Cron externe via cron-job.org (gratuit)

## Phase 2 — Scoring LLM (en cours)
- [x] Module scorer créé (`scorer.py`) avec prompt de scoring 0-10
- [x] Intégration dans `main.py` (score → priorité ntfy, détection doublons sémantiques)
- [x] Config `MIN_SCORE = 4` pour filtrer les articles peu pertinents
- [ ] **Activer le scoring** : la clé Gemini actuelle n'a pas de quota (facturation non activée)

### Options pour le LLM scorer
1. **Gemini Flash (gratuit)** — Activer la facturation sur Google Cloud (pas de frais, free tier suffisant). Clé actuelle : `AIzaSyAxEepAGEJ3mVvDIT6hC15W05jtM6uRhII`
2. **Groq (gratuit, sans carte)** — console.groq.com, Llama 3.3 70B, 30 req/min. Nécessite de modifier `scorer.py` pour utiliser l'API Groq
3. **Claude Haiku (payant ~$0.40/mois)** — console.anthropic.com, meilleure qualité

### Prochaines actions
1. Choisir et configurer un provider LLM fonctionnel
2. Ajouter `GEMINI_API_KEY` (ou `GROQ_API_KEY`) dans les variables Render du service news-fetcher
3. Tester le scoring en production
4. Redéployer sur Render

## Phase 3 — Confort (à venir)
- [ ] Web UI de gestion (CRUD keywords, edit prompt) — FastAPI + HTMX
- [ ] Stats et historique des notifs
- [ ] Dédoublonnage sémantique si nécessaire

## Phase 4 — Polish (optionnel)
- [ ] Authentification web UI
- [ ] Backup config/historique
- [ ] Mode "résumé quotidien"

## Infos déploiement
- **Repo** : https://github.com/BigStraat/news-feed
- **ntfy-server** : https://ntfy-server-906d.onrender.com
- **news-fetcher** : https://news-fetcher-d8ef.onrender.com
- **ntfy topic** : `news-feed-f0393738`
- **cron trigger** : GET `/run` avec header `X-Cron-Secret`
- **cron-job.org** : toutes les heures

## Notes
- GNews rate-limit la 2e requête quand elles sont trop rapprochées (429 sur le keyword "OpenAI") — pas bloquant, le script gère l'erreur
- La DB SQLite sur Render est en `/tmp` donc perdue entre redéploiements — acceptable pour le MVP, passer à Supabase en Phase 3
