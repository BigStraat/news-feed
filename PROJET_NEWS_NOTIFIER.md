# 📰 Projet News Notifier — Récapitulatif

## 🎯 Objectif

Application personnelle qui surveille l'actualité via des APIs de news, filtre les articles pertinents grâce à un scoring intelligent, et envoie des notifications push sur mon téléphone avec un niveau d'urgence adapté à l'importance de la news.

---

## 🏗️ Architecture globale

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  GNews API  │────▶│             │     │              │     │             │
│  (topic A)  │     │   Script    │────▶│  LLM Scorer  │────▶│  ntfy       │
├─────────────┤────▶│   Python    │     │  (Claude/    │     │  self-host  │
│ NewsData.io │     │  (cron job) │     │   autre)     │     │  sur Render │
│  (topic B)  │     │             │     │              │     │             │
└─────────────┘     └──────┬──────┘     └──────────────┘     └──────┬──────┘
                           │                                         │
                           ▼                                         ▼
                    ┌─────────────┐                          ┌─────────────┐
                    │  Web UI     │                          │  📱 App     │
                    │  (gestion   │                          │  ntfy sur   │
                    │  keywords)  │                          │  téléphone  │
                    └─────────────┘                          └─────────────┘
```

---

## 🔌 Sources de news

Stratégie : utiliser **deux APIs gratuites** sur des **sujets/topics différents** pour multiplier le quota disponible et diversifier les sources.

| API | Quota gratuit | Usage prévu |
|---|---|---|
| **GNews API** | 100 req/jour | Topics groupe A (à définir) |
| **NewsData.io** | 200 req/jour | Topics groupe B (à définir) |
| **Total** | **300 req/jour** | ~12 polls/heure combinés |

> ⚠️ NewsAPI.org écarté car son plan gratuit ne fonctionne qu'en localhost en production.

**À définir plus tard** : quels mots-clés/topics vont sur quelle API (logique de répartition à arbitrer selon la qualité des résultats observée).

---

## 📲 Notifications push : ntfy self-hosted

**Choix** : self-hosting de ntfy sur la même instance Render que le script.

**Pourquoi self-host plutôt que ntfy.sh public ?**
- Topics privés (les topics sur ntfy.sh sont publics, devinables)
- Pas de limite de débit imposée par un tiers
- Maîtrise complète des données

**Niveaux de priorité ntfy** (essentiels pour le projet) :

| Niveau | Comportement téléphone | Usage prévu |
|---|---|---|
| `min` (1) | Silencieux, juste dans la barre | News marginales, score très bas |
| `low` (2) | Pas de son, pas de vibration | News intéressantes mais non urgentes |
| `default` (3) | Son + vibration standard | News pertinentes normales |
| `high` (4) | Son long, vibration forte, notif épinglée | News importantes |
| `urgent` (5) | **Bypass mode silencieux/Ne-pas-déranger** | Breaking news critiques |

L'idée : **mapper le score de pertinence du LLM sur ces niveaux**, pour que mon téléphone réagisse différemment selon l'importance de la news.

---

## 🧠 Filtrage intelligent par scoring LLM

**Principe** : avant d'envoyer une notif, chaque article passe par un LLM qui lui attribue un score de pertinence de 0 à 10.

**Pipeline de scoring (à affiner)** :
1. Récupération brute des articles depuis GNews + NewsData
2. Pré-filtrage rapide (déjà vu ? doublon ? langue ?)
3. Envoi du titre + description au LLM avec un prompt qui décrit mes intérêts
4. Le LLM renvoie : `{ score: 0-10, raison: "...", priorité: "low|default|high|urgent" }`
5. Mapping score → priorité ntfy → envoi de la notif

**Mapping score → priorité (proposition de départ, à ajuster)** :

| Score | Priorité ntfy | Action |
|---|---|---|
| 0-3 | (pas de notif) | Article ignoré |
| 4-5 | `low` | Notif silencieuse |
| 6-7 | `default` | Notif standard |
| 8-9 | `high` | Notif appuyée |
| 10 | `urgent` | Bypass DND |

**LLM choisi** : **Claude Haiku 4.5** (`claude-haiku-4-5`)
- Rapide (~1s par scoring), peu coûteux (~0,001 $/article)
- API Anthropic, clé à mettre en variable d'environnement `ANTHROPIC_API_KEY`
- Prompt système à itérer selon résultats observés en Phase 2
- Avec 300 articles/jour max et un pré-filtrage par mots-clés, on reste largement sous 1 $/mois

---

## 🔁 Dédoublonnage

**Problème** : GNews et NewsData peuvent renvoyer le même article (même news reprise par plusieurs sources), et le cron tournant régulièrement risque de re-notifier.

**Stratégie en 2 niveaux** :

1. **Dédoublonnage par URL** (rapide, en DB) : hash de l'URL stocké dans Supabase avec TTL de 7 jours, vérifié avant tout traitement
2. **Dédoublonnage sémantique via le LLM scorer** : on tire parti du fait que Claude Haiku passe déjà sur chaque article. On lui envoie aussi les **5 derniers titres notifiés des dernières 6h** dans le contexte, et on lui demande de retourner un flag `is_duplicate: true/false` en plus du score. Si dup → on skip la notif.

**Pourquoi cette approche plutôt que des embeddings** :
- Pas de dépendance supplémentaire (pas besoin de modèle d'embeddings local ni d'API séparée)
- Coût marginal négligeable (quelques tokens en plus par requête Haiku)
- Le LLM est meilleur que la similarité cosine pure pour détecter "même news, angle différent"
- Reste simple à itérer : on ajuste le prompt si la détection est trop stricte/laxiste

---

## 🖥️ Web UI minimal

**Objectif** : pouvoir gérer la config sans redéployer à chaque fois.

**Fonctionnalités prévues** :
- Liste des mots-clés / topics actifs (CRUD)
- Répartition GNews vs NewsData
- Edition du prompt LLM de scoring (ce qui m'intéresse)
- Visualisation des dernières notifs envoyées + score attribué
- Statistiques basiques : quota API restant, nb de notifs/jour, etc.
- Bouton "test" pour envoyer une notif de vérification

**Stack retenue** :
- **Backend** : FastAPI (cohérent avec le script Python, async natif, génération auto de docs OpenAPI)
- **Frontend** : HTML + Jinja2 templates + **HTMX** pour l'interactivité
- **Styling** : Tailwind via CDN (zéro build step)
- **Stockage** : Supabase (cf. section Hébergement)

**Pourquoi cette stack** : pas de build frontend, pas de framework JS lourd, on reste sur un seul process Python qui sert tout. Idéal pour un projet perso, déploiement trivial sur Render, et HTMX gère bien les besoins (formulaires, mises à jour partielles, listes dynamiques) sans complexité.

**Authentification** : Basic Auth via FastAPI sur toutes les routes UI (suffisant pour usage perso, identifiants en variables d'env).

---

## ☁️ Hébergement : Render

**Composants à déployer** :

| Service Render | Type | Rôle |
|---|---|---|
| `news-fetcher` | Cron Job | Exécution périodique du script de polling + scoring |
| `ntfy-server` | Web Service | Instance ntfy self-hosted |
| `web-ui` | Web Service | Interface de gestion |

**Solution keep-alive ntfy** : **cron-job.org** (gratuit, sans compte requis pour usage simple)
- Service externe qui ping notre instance ntfy toutes les 10 minutes
- Empêche le free tier Render de mettre le service en veille
- Alternative interne : faire que notre propre cron `news-fetcher` ping ntfy en début d'exécution (suffit si la fréquence est ≥ toutes les 10 min)
- **Choix retenu** : ping interne depuis `news-fetcher` (zéro dépendance externe, plus simple)

> Si ça ne suffit pas en pratique (latence au réveil sur les notifs urgentes), on basculera ntfy sur **Fly.io** dont le free tier inclut un service toujours actif (256 Mo RAM, largement assez pour ntfy).
- **Base de données** : **Supabase** (Postgres managé, free tier 500 Mo + 2 projets actifs)
  - Stocke : config keywords, historique articles vus (dédoublonnage), historique notifs envoyées avec scores, prompt LLM éditable
  - Connexion via `psycopg` ou `supabase-py` selon ce qui est le plus pratique
  - ⚠️ Le free tier Supabase met les projets en pause après 1 semaine d'inactivité — vu qu'on aura un cron qui tape la DB toutes les heures, pas de souci

---

## 📅 Roadmap proposée

**Phase 1 — MVP fonctionnel**
- [ ] Inscription GNews + NewsData, récupération des clés
- [ ] Self-host ntfy sur Render + app mobile configurée
- [ ] Script Python qui poll les 2 APIs et envoie via ntfy (sans LLM, sans UI)
- [ ] Dédoublonnage simple par URL
- [ ] Déploiement en cron job sur Render

**Phase 2 — Intelligence**
- [ ] Intégration LLM scorer (Claude Haiku probablement)
- [ ] Mapping score → priorité ntfy
- [ ] Tuning du prompt système selon les résultats observés

**Phase 3 — Confort**
- [ ] Web UI de gestion (CRUD keywords, edit prompt)
- [ ] Stats et historique des notifs
- [ ] Dédoublonnage sémantique si nécessaire

**Phase 4 — Polish (optionnel)**
- [ ] Authentification web UI
- [ ] Backup config/historique
- [ ] Mode "résumé quotidien" en plus des notifs temps réel

---

## 🔑 Variables d'environnement (récap)

À configurer sur Render pour les différents services :

| Variable | Service(s) | Description |
|---|---|---|
| `GNEWS_API_KEY` | news-fetcher | Clé GNews |
| `NEWSDATA_API_KEY` | news-fetcher | Clé NewsData.io |
| `ANTHROPIC_API_KEY` | news-fetcher | Clé API Anthropic pour Claude Haiku |
| `NTFY_SERVER_URL` | news-fetcher, web-ui | URL de notre instance ntfy self-hosted |
| `NTFY_TOPIC` | news-fetcher, web-ui | Nom du topic privé |
| `NTFY_AUTH_TOKEN` | news-fetcher, web-ui | Token pour publier sur l'instance privée |
| `SUPABASE_URL` | news-fetcher, web-ui | URL projet Supabase |
| `SUPABASE_KEY` | news-fetcher, web-ui | Clé service Supabase |
| `WEB_UI_USER` | web-ui | Identifiant Basic Auth |
| `WEB_UI_PASSWORD` | web-ui | Mot de passe Basic Auth |

---

## ❓ Décisions encore à prendre

1. **Répartition des topics** entre GNews et NewsData → à arbitrer en Phase 1 selon qualité des résultats observée

> Toutes les autres décisions techniques sont arbitrées. ✅
