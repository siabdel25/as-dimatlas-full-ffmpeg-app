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
| 🎬 **Medley** | Assemble 2 à 12 extraits en une vidéo : ordre par glisser-déposer, découpage A/B par clip, transition xfade réglable entre chaque clip, aperçu rapide basse résolution, export 480p/720p/1080p |
| 📻 **Radio** | 18 stations marocaines intégrées, recherche dans l'annuaire mondial Radio Browser, favoris ⭐ (localStorage), flux personnalisé : écoute en direct (titre en cours via ICY) et enregistrement MP3 avec arrêt anticipé |
| 🖼️ **Images** | Découpe la vidéo en images JPEG/PNG (1 toutes les N secondes), livrées en ZIP |
| 🎼 **Bande musicale** | Associe un audio à une vidéo : remplacement ou mixage avec le son d'origine |
| 🔤 **Titre** | Incruste un texte (position, couleur, contour noir) sur la vidéo |
| ✨ **Effets** | Transition d'intro/outro (fondu noir ou blanc, cercle, zoom, pixellisation…) avec fondu du son assorti |
| 📂 **Bibliothèque** | Tous les fichiers produits, consultables en un clic, avec vignette (image de la vidéo, pochette de l'audio) |
| ⚙️ **Paramètres** | Pochette audio (auto-extraction ou non, résolution), nombre de miniatures dans la timeline, nombre d'encodeurs ffmpeg simultanés — sans éditer le code |

Les vidéos vont dans `downloads/`, les audios dans `audio/`. Aucun fichier
n'est jamais écrasé (suffixes `_1`, `_2`, …). Partout où l'on choisit un
fichier (découpage, medley, images, bande musicale, titre, effets,
extraction audio) comme dans la Bibliothèque : un champ de recherche filtre
la liste par nom, chaque ligne est numérotée et affiche sa date de création,
la liste est triée du plus récent au plus ancien.

Les encodages passent par une **file d'attente** (2 ffmpeg simultanés par
défaut, réglable dans l'onglet **Paramètres** ou via la variable
d'environnement `ENCODERS` — le réglage UI prend le dessus s'il est défini,
nécessite un redémarrage pour s'appliquer) : les tâches supplémentaires
affichent « En file d'attente » puis démarrent dès qu'un encodeur se libère.
Les téléchargements YouTube et les enregistrements radio, limités par le
réseau, ne comptent pas dans cette limite.

## Démarrage rapide

### Avec Docker (recommandé)

```bash
docker compose up -d
```

Puis ouvrez **http://localhost:5000**. Les dossiers `downloads/`, `audio/`
et `config/` (réglages de l'onglet Paramètres) sont montés en volumes : les
fichiers et réglages restent sur votre machine, y compris après un
`docker compose up -d --build`.

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
| `/api/medley` | POST | `{clips: [{file, t1, t2}], transitions: [{type, duration}], resolution, bitrate, preview}` |
| `/api/medley/transitions` | GET | — |
| `/api/medley/preview` | GET | — (dernier aperçu généré) |
| `/api/radio/stations` | GET | — |
| `/api/radio/search` | GET | `?q=<nom>` (annuaire Radio Browser) |
| `/api/radio/nowplaying` | GET | `?url=<flux>` |
| `/api/radio/record` | POST | `{url, name, minutes}` |
| `/api/frames` | POST | `{file, format, every}` |
| `/api/music` | POST | `{video, audio, mode: replace\|mix}` |
| `/api/text` | POST | `{file, text, position, color}` |
| `/api/effects` | GET | — (liste des effets) |
| `/api/effects` | POST | `{file, effect, where: intro\|outro\|both, duration}` |
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
