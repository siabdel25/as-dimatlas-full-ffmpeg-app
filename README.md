# 🎬 VideoCoder Studio

Boîte à outils vidéo/audio auto-hébergée : une application web (Flask + Vue 3)
qui enveloppe **ffmpeg** et **yt-dlp** dans une interface simple, avec
progression des traitements en temps réel.

## Fonctionnalités

| Outil | Description |
|---|---|
| 🎥 **YouTube** | Téléchargement d'une vidéo en MP4 (métadonnées, miniature, barre de progression) |
| 💬 **Réseaux sociaux** | Conversion WhatsApp/Instagram : H.264 + AAC, `yuv420p`, `faststart`, débit calculé selon la durée pour viser < 16 Mo |
| 🎵 **Extraction audio** | Piste audio d'une vidéo en mp3, aac, ogg, wav ou flac |
| ✂️ **Découpage** | Extrait de t1 à t2 (minutes décimales `1.5` ou `mm:ss`), coupe précise à l'image |
| 📻 **Radio** | 18 stations marocaines intégrées + flux personnalisé : écoute en direct (titre en cours via ICY) et enregistrement MP3 avec arrêt anticipé |
| 🖼️ **Images** | Découpe la vidéo en images JPEG/PNG (1 toutes les N secondes), livrées en ZIP |
| 🎼 **Bande musicale** | Associe un audio à une vidéo : remplacement ou mixage avec le son d'origine |
| 🔤 **Titre** | Incruste un texte (position, couleur, contour noir) sur la vidéo |
| 📂 **Bibliothèque** | Tous les fichiers produits, consultables en un clic |

Les vidéos vont dans `downloads/`, les audios dans `audio/`. Aucun fichier
n'est jamais écrasé (suffixes `_1`, `_2`, …).

## Démarrage rapide

### Avec Docker (recommandé)

```bash
docker compose up -d
```

Puis ouvrez **http://localhost:5000**. Les dossiers `downloads/` et `audio/`
sont montés en volumes : les fichiers restent sur votre machine.

```bash
docker compose down              # arrêter
docker compose up -d --build     # reconstruire après une modif (ou pour mettre à jour yt-dlp)
```

### Sans Docker

Prérequis : Python 3.9+ et ffmpeg (`sudo apt install ffmpeg`).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

### Version ligne de commande

Les mêmes outils de base existent en CLI à menu, sans serveur :

```bash
.venv/bin/python scrap_movie.py
```

## API

Toutes les opérations longues renvoient un `task_id` à interroger sur
`GET /api/tasks/<id>` (progression 0–100, statut, fichier produit).

| Endpoint | Méthode | Corps (JSON) |
|---|---|---|
| `/api/files` | GET | — |
| `/api/youtube/info` | POST | `{url}` |
| `/api/youtube/download` | POST | `{url}` |
| `/api/convert` | POST | `{file}` |
| `/api/audio/extract` | POST | `{file, format}` |
| `/api/cut` | POST | `{file, t1, t2}` (secondes) |
| `/api/radio/stations` | GET | — |
| `/api/radio/nowplaying` | GET | `?url=<flux>` |
| `/api/radio/record` | POST | `{url, name, minutes}` |
| `/api/frames` | POST | `{file, format, every}` |
| `/api/music` | POST | `{video, audio, mode: replace\|mix}` |
| `/api/text` | POST | `{file, text, position, color}` |
| `/api/tasks/<id>` | GET | — |
| `/api/tasks/<id>/stop` | POST | — (garde le fichier partiel) |
| `/api/media/<video\|audio>/<nom>` | GET | — |

## Structure

```
app.py                  API Flask + tâches de fond ffmpeg/yt-dlp
static/                 SPA Vue 3 + Vue Router + Bootstrap 5
  index.html            coquille (sidebar, thème sombre/clair)
  app.js                composants et vues
  app.css               design system (tokens, responsive)
scrap_movie.py          version CLI à menu
Dockerfile              python:3.13-slim + ffmpeg + fonts-dejavu
docker-compose.yml      port 5000, volumes downloads/ et audio/
```

## Limites à connaître

- **WhatsApp** : ~16 Mo par vidéo ; un statut est limité à 90 s (l'app avertit).
- **yt-dlp** vieillit vite : si les téléchargements YouTube échouent,
  mettez à jour (`pip install -U yt-dlp` ou `docker compose build --no-cache`).
- **Titre incrusté** : la police (DejaVu) ne rend pas les émojis.
- L'app est prévue pour un usage **local** (pas d'authentification).
