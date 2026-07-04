---
name: ffmpeg-media
description: Traitement vidéo/audio avec ffmpeg — conversion pour réseaux sociaux (WhatsApp, Instagram), extraction audio, découpage, redimensionnement, inspection. À utiliser dès qu'une tâche implique ffmpeg, ffprobe, yt-dlp ou la manipulation de fichiers vidéo/audio dans ce projet.
---

# Traitement vidéo / audio avec ffmpeg

## Contexte du projet

- Dossiers : `downloads/` (vidéos), `audio/` (sorties audio).
- `scrap_movie.py` est le script à menu du projet (téléchargement YouTube, conversion réseaux sociaux, extraction audio, découpage). Réutiliser ses fonctions plutôt que de dupliquer la logique.
- Python : `.venv/bin/python` (yt-dlp installé dans le venv) ; ffmpeg/ffprobe système.

## Inspection d'un fichier

```bash
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=codec_name,codec_type,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 "fichier.mp4"
```

## Conversion WhatsApp / Instagram (paramètres validés)

Codecs exigés : H.264 (profil main) + AAC, `yuv420p` (évite les écrans noirs/verts), `+faststart` (lecture en streaming immédiate).

```bash
ffmpeg -y -i in.mp4 \
  -c:v libx264 -profile:v main -level 4.0 -pix_fmt yuv420p \
  -b:v 500k -maxrate 600k -bufsize 1200k -preset medium -r 30 \
  -c:a aac -b:a 96k -ar 44100 \
  -movflags +faststart out_whatsapp.mp4
```

- Calculer le débit vidéo selon la durée pour viser ~14 Mo :
  `debit_kbps = 14*8192/duree_s - 96`, borné à [300, 2000].
- Limites à signaler : WhatsApp ~16 Mo par vidéo, statut WhatsApp 90 s max,
  Reel Instagram 90 s (jusqu'à 15 min en post vidéo).
- Ne PAS utiliser CRF seul pour ces cibles : la taille n'est pas prévisible
  (un CRF 23 a produit 22 Mo là où le débit ciblé donnait 12 Mo).

## Extraction audio

```bash
ffmpeg -y -i in.mp4 -vn -map a -c:a libmp3lame -b:a 192k audio/out.mp3
```

Codecs par format : mp3→`libmp3lame -b:a 192k` · aac→`aac -b:a 192k` (ext `.m4a`)
· ogg→`libvorbis -q:a 5` · wav→`pcm_s16le` · flac→`flac`.

## Découpage précis (t1 → t2)

```bash
ffmpeg -y -ss 30.000 -to 60.000 -i in.mp4 \
  -c:v libx264 -crf 22 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 128k -movflags +faststart out_extrait.mp4
```

- Ré-encoder (pas `-c copy`) : la copie coupe sur les images clés → début figé/décalé.
- `-ss` avant `-i` = seek rapide ; avec ré-encodage la coupe reste précise à l'image.
- `-c copy` acceptable seulement si l'utilisateur veut la vitesse et tolère
  une coupe approximative (±quelques secondes).

## Autres recettes utiles

```bash
# Redimensionner (hauteur auto, divisible par 2 — requis par yuv420p)
-vf "scale=720:-2"

# Format carré 1:1 avec bandes floues (post Instagram)
-vf "split[a][b];[a]scale=720:720,boxblur=20[bg];[b]scale=720:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"

# Vertical 9:16 (Reel/Story) : recadrage centré
-vf "crop=ih*9/16:ih,scale=720:1280"

# GIF de qualité (palette)
ffmpeg -ss 5 -t 3 -i in.mp4 -vf "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" out.gif

# Vitesse x2 (vidéo + audio)
-vf "setpts=PTS/2" -af "atempo=2"
```

## Bonnes pratiques

- Toujours `ffprobe` la source avant d'encoder (codec, résolution, durée).
- Vérifier la taille du résultat après encodage et la comparer aux limites de la plateforme cible.
- Ne jamais écraser la source ; suffixer la sortie (`_whatsapp`, `_extrait_…`).
- Noms de fichiers avec émojis/espaces : toujours entre guillemets doubles.
- yt-dlp : format `bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best` pour un mp4 exploitable.
