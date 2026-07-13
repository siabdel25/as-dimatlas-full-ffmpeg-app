#!/usr/bin/env python3
"""
app.py — API Flask de la boîte à outils vidéo/audio (frontend Vue dans static/).

Endpoints :
    GET  /api/files                    Liste des vidéos (downloads/) et audios (audio/)
    POST /api/youtube/info             Métadonnées d'une URL YouTube
    POST /api/youtube/download         Téléchargement (tâche de fond)
    POST /api/convert                  Conversion WhatsApp/Instagram (tâche de fond)
    POST /api/audio/extract            Extraction audio mp3/aac/ogg/wav/flac (tâche de fond)
    POST /api/cut                      Découpage t1→t2 en secondes (tâche de fond)
    GET  /api/tasks/<id>               État/progression d'une tâche
    GET  /api/media/<type>/<nom>       Téléchargement du fichier produit
    GET  /api/settings                 Paramètres actuels (pochette, encodeurs, miniatures)
    POST /api/settings                 Mise à jour des paramètres (validation stricte)

Lancement : .venv/bin/python app.py  →  http://localhost:5000
"""

import base64
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import uuid

from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v")

# Paramètres persistés (dashboard Paramètres). Volume Docker dédié
# (docker-compose.yml : ./config:/app/config) — un emplacement hors volume
# monté serait effacé à chaque `docker compose up -d --build`.
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CONFIG_LOCK = threading.Lock()

CONFIG_DEFAULTS = {
    "pochette_auto": True,       # extraction depuis la vidéo si pas d'upload utilisateur
    "pochette_resolution": 500,  # largeur en px (scale=X:-2)
    "nb_encodeurs": None,        # None = pas de préférence -> fallback env ENCODERS / défaut
    "nb_miniatures": 16,
    "qualite_video": "equilibre",
}

BORNES_SETTINGS = {
    "pochette_resolution": (64, 2000),
    "nb_encodeurs": (1, 8),
    "nb_miniatures": (4, 40),
}

# Un seul contrôle qualitatif (pas de CRF/preset bruts exposés en UI —
# décision Design) qui pilote vitesse/qualité d'encodage x264 ET le débit
# audio par défaut. `crf` ne s'applique qu'aux sites qui encodent déjà en
# mode CRF ; `preset` s'applique aussi à Conversion réseaux sociaux et à la
# branche débit explicite du Medley (orthogonal au mode bitrate) ;
# `audio_kbps` ne s'applique PAS à Conversion réseaux sociaux (son débit
# audio est déjà compté dans le calcul du budget <16 Mo) ni à l'aperçu
# Medley (reste rapide par construction, jamais affecté par ce réglage).
QUALITES_VIDEO = {
    "leger":     {"crf": 28, "preset": "fast",   "audio_kbps": 96},
    "equilibre": {"crf": 22, "preset": "medium", "audio_kbps": 128},
    "max":       {"crf": 18, "preset": "slow",   "audio_kbps": 192},
}


def _qualite_video():
    """Valeurs qualité effectives (crf/preset/audio_kbps). Fallback sur
    "equilibre" si CONFIG contient une clé invalide (édition manuelle
    ratée) — appelée au call-time (pas au chargement du module), donc une
    valeur corrompue ne peut jamais empêcher un export vidéo de démarrer."""
    return QUALITES_VIDEO.get(CONFIG.get("qualite_video"), QUALITES_VIDEO["equilibre"])


def _charger_config():
    """Fusionne config.json sur les défauts. Un fichier absent, corrompu ou
    partiellement écrit ne doit jamais empêcher l'app de démarrer — on
    retombe silencieusement sur les défauts plutôt que de laisser
    l'exception remonter jusqu'à l'import du module."""
    config = dict(CONFIG_DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            disque = json.load(f)
        if isinstance(disque, dict):
            config.update({k: v for k, v in disque.items() if k in CONFIG_DEFAULTS})
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        pass
    return config


CONFIG = _charger_config()

AUDIO_FORMATS = {
    "mp3":  {"ext": "mp3",  "args": ["-c:a", "libmp3lame", "-b:a", "192k"]},
    "aac":  {"ext": "m4a",  "args": ["-c:a", "aac", "-b:a", "192k"]},
    "ogg":  {"ext": "ogg",  "args": ["-c:a", "libvorbis", "-q:a", "5"]},
    "wav":  {"ext": "wav",  "args": ["-c:a", "pcm_s16le"]},
    "flac": {"ext": "flac", "args": ["-c:a", "flac"]},
}

# Conteneurs sachant embarquer une image de pochette (attached_pic) : wav n'a
# pas de mécanisme standard de métadonnées image, et ogg/vorbis refuse le
# flux mjpeg en attached_pic (Unsupported codec id in stream).
FORMATS_POCHETTE = {"mp3", "aac", "flac"}

# Stations avec une URL de flux directe (les pages web sans flux sont exclues).
RADIO_STATIONS = [
    {"name": "Aswat", "genre": "Généraliste", "url": "https://broadcast.ice.infomaniak.ch/aswat-high.mp3"},
    {"name": "Medi1 Radio", "genre": "Généraliste, Actualités", "url": "https://streaming1.medi1tv.com/radio/radio_mag.stream_aac/playlist.m3u8"},
    {"name": "Hit Radio Mgharba", "genre": "Hits marocains", "url": "https://mgharba.ice.infomaniak.ch/mgharba-128.mp3"},
    {"name": "Radio Amazighia", "genre": "Culturelle", "url": "https://cdnamd-hls-globecast.akamaized.net/live/ramdisk/radio_amazigh/hls_snrt_radio/index.m3u8"},
    {"name": "Medina FM", "genre": "Généraliste", "url": "https://medinafm.ice.infomaniak.ch/medinafm-64.mp3"},
    {"name": "Marrakech Plus", "genre": "Locale — Marrakech", "url": "https://cast5.my-control-panel.com/proxy/marrakec/stream"},
    {"name": "Atlantic Radio", "genre": "Généraliste — Casablanca", "url": "https://atlantic-sonic.nindohost.net:9300/stream/1/"},
    {"name": "Radio Mars", "genre": "Sport", "url": "https://radiomars.ice.infomaniak.ch/radiomars-128.mp3"},
    {"name": "MFM Radio", "genre": "Généraliste", "url": "https://a5.asurahosting.com:7980/radio.mp3"},
    {"name": "Radio Soleil", "genre": "Généraliste", "url": "https://radiosoleil.ice.infomaniak.ch/radiosoleil-128.mp3"},
    {"name": "Radio Tanger Med", "genre": "Locale — Tanger", "url": "https://radiotangermed-22.ice.infomaniak.ch/radiotangermed-22-128.mp3"},
    {"name": "Oxygene FM", "genre": "Généraliste", "url": "https://radiocampus.ice.infomaniak.ch/radiocampus-128.mp3"},
    {"name": "NRJ Maroc", "genre": "Hits, Pop", "url": "https://icecast.nrjmaroc.com/stream"},
    {"name": "Cap Radio", "genre": "Généraliste — Nord", "url": "https://listen.radioking.com/radio/710810/stream/776366"},
    {"name": "Radio Manarat", "genre": "Culturelle, Éducative", "url": "https://listen.radioking.com/radio/252934/stream/297385"},
    {"name": "Radio Yabiladi", "genre": "Maghrébine", "url": "https://radio.yabiladi.com:8002/stream/1/"},
    {"name": "4U Classic Rock", "genre": "Rock", "url": "https://str4uice.streamakaci.com/4uclassicrock.mp3"},
    {"name": "Radio Star Maroc FM", "genre": "Généraliste", "url": "https://a2.asurahosting.com:6100/stream/1/"},
]

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

TASKS = {}
PROCS = {}
TASKS_LOCK = threading.Lock()


# ---------------------------------------------------------------- utilitaires

def new_task(kind):
    task_id = uuid.uuid4().hex[:12]
    with TASKS_LOCK:
        TASKS[task_id] = {"id": task_id, "kind": kind, "status": "running",
                          "progress": 0, "message": "Démarrage…", "output": None}
    return task_id


def update_task(task_id, **champs):
    with TASKS_LOCK:
        TASKS[task_id].update(champs)


# File d'attente des encodages : limite les ffmpeg simultanés pour que N
# tâches lancées d'affilée ne se partagent pas le CPU (statut "queued" en
# attendant). Les tâches réseau (YouTube, radio) restent en threads directs :
# elles ne pèsent pas sur le CPU et l'enregistrement radio, potentiellement
# long, monopoliserait un encodeur.
ENCODE_QUEUE = queue.Queue()


def _nb_encodeurs_configure():
    """Précédence : config.json > variable d'env ENCODERS > défaut 2.
    Un config.json syntaxiquement valide mais avec un type incorrect pour
    cette clé (édition manuelle ratée) ne doit pas empêcher l'app de
    démarrer — mêmes garanties que _charger_config()."""
    if CONFIG.get("nb_encodeurs") is not None:
        lo, hi = BORNES_SETTINGS["nb_encodeurs"]
        try:
            return max(lo, min(hi, int(CONFIG["nb_encodeurs"])))
        except (TypeError, ValueError):
            pass
    return max(1, int(os.environ.get("ENCODERS", "2")))


# Lu UNE SEULE FOIS au chargement du module pour lancer les threads workers
# ci-dessous : un changement via /api/settings met à jour CONFIG en mémoire
# (valeur "configured") mais ne peut pas relancer des threads déjà démarrés
# (valeur "active") — d'où la distinction exposée par GET /api/settings.
NB_ENCODEURS = _nb_encodeurs_configure()


def soumettre_encodage(task_id, fn):
    update_task(task_id, status="queued",
                message=f"En file d'attente ({ENCODE_QUEUE.qsize() + 1})…")
    ENCODE_QUEUE.put((task_id, fn))


def _boucle_encodeur():
    while True:
        task_id, fn = ENCODE_QUEUE.get()
        update_task(task_id, status="running", message="Démarrage…")
        try:
            fn()
        except Exception as exc:                # tâche suivante quoi qu'il arrive
            update_task(task_id, status="error", message=str(exc))
        finally:
            ENCODE_QUEUE.task_done()


for _ in range(NB_ENCODEURS):
    threading.Thread(target=_boucle_encodeur, daemon=True).start()


def fichier_video_valide(nom):
    """Résout un nom de fichier client vers downloads/ en bloquant les traversées."""
    chemin = os.path.normpath(os.path.join(DOWNLOADS_DIR, nom))
    if not chemin.startswith(DOWNLOADS_DIR + os.sep) or not os.path.isfile(chemin):
        return None
    return chemin


def chemin_sans_ecrasement(chemin):
    if not os.path.exists(chemin):
        return chemin
    base, ext = os.path.splitext(chemin)
    n = 1
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


CACHE_DUREE = {}  # chemin -> (mtime, duree) ; évite de rappeler ffprobe sur
                  # un fichier inchangé à chaque rafraîchissement de la liste.


def duree_video(chemin):
    mtime = os.path.getmtime(chemin)
    en_cache = CACHE_DUREE.get(chemin)
    if en_cache and en_cache[0] == mtime:
        return en_cache[1]
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", chemin],
        capture_output=True, text=True)
    try:
        duree = float(res.stdout.strip())
    except ValueError:
        duree = None
    CACHE_DUREE[chemin] = (mtime, duree)
    return duree


def lancer_ffmpeg(task_id, args, sortie, duree_totale):
    """Exécute ffmpeg en publiant la progression dans TASKS via -progress."""
    cmd = ["ffmpeg", "-hide_banner", "-y"] + args + \
          ["-progress", "pipe:1", "-nostats", sortie]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    with TASKS_LOCK:
        PROCS[task_id] = proc
    for ligne in proc.stdout:
        m = re.match(r"out_time_ms=(\d+)", ligne)
        if m and duree_totale:
            pct = min(99, int(int(m.group(1)) / 1e6 / duree_totale * 100))
            update_task(task_id, progress=pct,
                        message=f"Encodage… {pct} %")
    proc.wait()
    with TASKS_LOCK:
        PROCS.pop(task_id, None)
        arrete = TASKS[task_id].get("stopping")
    if proc.returncode != 0:
        # Arrêt volontaire : le fichier partiel est valide, on le garde.
        if arrete and os.path.exists(sortie) and os.path.getsize(sortie) > 0:
            return True
        err = "\n".join(proc.stderr.read().splitlines()[-4:])
        update_task(task_id, status="error", message=err or "Interrompu")
        if os.path.exists(sortie):
            os.remove(sortie)
        return False
    return True


def terminer(task_id, sortie, avertissements=None):
    dossier = "audio" if sortie.startswith(AUDIO_DIR) else "video"
    update_task(task_id, status="done", progress=100,
                message="Terminé",
                output={"name": os.path.basename(sortie),
                        "size": os.path.getsize(sortie),
                        "type": dossier,
                        "warnings": avertissements or []})


# -------------------------------------------------------------------- routes

@app.get("/")
def index():
    return send_from_directory("static", "index.html")


def valider_settings(payload):
    """Valide un payload de settings entrant contre BORNES_SETTINGS.
    Retourne (valeurs_validees, erreurs) ; en cas d'erreur, rien n'est
    écrit sur disque par l'appelant (POST /api/settings)."""
    if not isinstance(payload, dict):
        return {}, ["Le corps de la requête doit être un objet JSON"]

    valeurs = {}
    erreurs = []

    if "pochette_auto" in payload:
        if isinstance(payload["pochette_auto"], bool):
            valeurs["pochette_auto"] = payload["pochette_auto"]
        else:
            erreurs.append("pochette_auto doit être un booléen")

    if "qualite_video" in payload:
        if payload["qualite_video"] in QUALITES_VIDEO:
            valeurs["qualite_video"] = payload["qualite_video"]
        else:
            erreurs.append(
                f"qualite_video doit être l'un de {', '.join(QUALITES_VIDEO)}")

    for cle in ("pochette_resolution", "nb_encodeurs", "nb_miniatures"):
        if cle in payload:
            v = payload[cle]
            lo, hi = BORNES_SETTINGS[cle]
            if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi:
                valeurs[cle] = v
            else:
                erreurs.append(f"{cle} doit être un entier entre {lo} et {hi}")

    cles_inconnues = set(payload) - set(CONFIG_DEFAULTS)
    if cles_inconnues:
        erreurs.append(f"Clé(s) inconnue(s) : {', '.join(sorted(cles_inconnues))}")

    return valeurs, erreurs


def _settings_effectifs():
    # Clé normalisée : si CONFIG contient une valeur invalide (édition
    # manuelle ratée), on expose "equilibre" plutôt que la valeur brute —
    # cohérent avec le fallback silencieux de _qualite_video().
    qualite = CONFIG.get("qualite_video")
    if qualite not in QUALITES_VIDEO:
        qualite = "equilibre"
    return {
        "pochette_auto": CONFIG["pochette_auto"],
        "pochette_resolution": CONFIG["pochette_resolution"],
        "nb_miniatures": CONFIG["nb_miniatures"],
        "qualite_video": qualite,
        "nb_encodeurs": {
            "active": NB_ENCODEURS,
            "configured": CONFIG.get("nb_encodeurs") or NB_ENCODEURS,
        },
    }


@app.get("/api/settings")
def obtenir_settings():
    return jsonify(_settings_effectifs())


@app.post("/api/settings")
def sauvegarder_settings():
    payload = request.json or {}
    valeurs, erreurs = valider_settings(payload)
    if erreurs:
        return jsonify({"error": " ; ".join(erreurs)}), 400

    with CONFIG_LOCK:
        CONFIG.update(valeurs)
        os.makedirs(CONFIG_DIR, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(CONFIG, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, CONFIG_PATH)
        except OSError:
            os.unlink(tmp_path)
            raise

    reponse = _settings_effectifs()
    reponse["restart_required"] = (
        "nb_encodeurs" in valeurs and valeurs["nb_encodeurs"] != NB_ENCODEURS
    )
    return jsonify(reponse)


def parcourir(racine, ignorer_dirs=()):
    """Parcourt racine récursivement, donnant (chemin_absolu, nom_relatif)."""
    if not os.path.isdir(racine):
        return
    for base, dirs, fichiers in os.walk(racine):
        dirs[:] = [d for d in sorted(dirs) if d not in ignorer_dirs]
        for f in sorted(fichiers):
            chemin = os.path.join(base, f)
            relatif = os.path.relpath(chemin, racine).replace(os.sep, "/")
            yield chemin, relatif


@app.get("/api/files")
def liste_fichiers():
    videos, audios, exports = [], [], []
    for chemin, relatif in parcourir(DOWNLOADS_DIR, ignorer_dirs=(".miniatures",)):
        if relatif.lower().endswith(VIDEO_EXTS):
            videos.append({"name": relatif, "size": os.path.getsize(chemin),
                           "duration": duree_video(chemin),
                           "created": os.path.getmtime(chemin)})
        elif relatif.lower().endswith(".zip"):
            exports.append({"name": relatif, "size": os.path.getsize(chemin),
                            "created": os.path.getmtime(chemin)})
    for chemin, relatif in parcourir(AUDIO_DIR):
        audios.append({"name": relatif, "size": os.path.getsize(chemin),
                       "created": os.path.getmtime(chemin)})
    # Plus récent en premier : c'est l'ordre le plus utile dans une
    # bibliothèque qui ne fait que grossir.
    for liste in (videos, audios, exports):
        liste.sort(key=lambda o: o["created"], reverse=True)
    return jsonify({"videos": videos, "audios": audios, "exports": exports})


@app.get("/api/media/<dossier>/<path:nom>")
def servir_media(dossier, nom):
    racine = {"video": DOWNLOADS_DIR, "audio": AUDIO_DIR}.get(dossier)
    if not racine:
        abort(404)
    return send_from_directory(racine, nom, as_attachment=False)


@app.get("/api/tasks/<task_id>")
def etat_tache(task_id):
    with TASKS_LOCK:
        tache = TASKS.get(task_id)
    if not tache:
        abort(404)
    return jsonify(tache)


@app.post("/api/youtube/info")
def youtube_info():
    from yt_dlp import YoutubeDL
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL manquante"}), 400
    try:
        with YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"error": f"Vidéo introuvable : {e}"}), 400
    return jsonify({
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "views": info.get("view_count"),
        "thumbnail": info.get("thumbnail"),
    })


@app.post("/api/youtube/download")
def youtube_download():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL manquante"}), 400
    task_id = new_task("download")

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                pct = int(d.get("downloaded_bytes", 0) / total * 100)
                update_task(task_id, progress=min(pct, 99),
                            message=f"Téléchargement… {pct} %")
        elif d["status"] == "finished":
            update_task(task_id, progress=99, message="Finalisation…")

    def travail():
        from yt_dlp import YoutubeDL
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        opts = {
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
            "outtmpl": f"{DOWNLOADS_DIR}/%(title)s.%(ext)s",
            "noplaylist": True, "quiet": True, "no_warnings": True,
            "progress_hooks": [hook],
        }
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                sortie = ydl.prepare_filename(info)
            terminer(task_id, sortie)
        except Exception as e:
            update_task(task_id, status="error", message=str(e))

    threading.Thread(target=travail, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.post("/api/convert")
def convertir():
    nom = (request.json or {}).get("file", "")
    source = fichier_video_valide(nom)
    if not source:
        return jsonify({"error": "Fichier introuvable"}), 400
    duree = duree_video(source)
    if not duree:
        return jsonify({"error": "Durée illisible"}), 400
    task_id = new_task("convert")

    def travail():
        # -crf et le débit audio restent volontairement exclus du réglage
        # qualité global : le calcul ci-dessous garantit <16 Mo en
        # réservant un débit audio fixe dans le budget total, changer l'un
        # sans recalculer l'autre romprait cette garantie de taille.
        # -preset reste orthogonal (vitesse/efficacité, pas la taille).
        debit = max(300, min(int(14 * 8192 / duree) - 96, 2000))
        preset = _qualite_video()["preset"]
        sortie = chemin_sans_ecrasement(
            os.path.splitext(source)[0] + "_whatsapp.mp4")
        ok = lancer_ffmpeg(task_id, [
            "-i", source,
            "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
            "-pix_fmt", "yuv420p",
            "-b:v", f"{debit}k", "-maxrate", f"{int(debit * 1.2)}k",
            "-bufsize", f"{debit * 2}k",
            "-preset", preset, "-r", "30",
            "-c:a", "aac", "-b:a", "96k", "-ar", "44100",
            "-movflags", "+faststart",
        ], sortie, duree)
        if ok:
            avert = []
            if os.path.getsize(sortie) > 16 * 1024 * 1024:
                avert.append("Fichier > 16 Mo (limite vidéo WhatsApp)")
            if duree > 90:
                avert.append("Durée > 90 s : trop long pour un statut "
                             "WhatsApp (OK en message et en Reel)")
            terminer(task_id, sortie, avert)

    soumettre_encodage(task_id, travail)
    return jsonify({"task_id": task_id})


def extraire_pochette(chemin, duree):
    """Image de la vidéo (à 10 % de la durée) à embarquer comme pochette
    audio ; None si l'extraction échoue (vidéo sans piste vidéo, etc.)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    resolution = CONFIG.get("pochette_resolution", 500)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{duree * 0.1:.2f}",
             "-i", chemin, "-frames:v", "1", "-vf", f"scale={resolution}:-2", tmp.name],
            capture_output=True)
    except OSError:
        os.unlink(tmp.name)
        raise
    if not os.path.getsize(tmp.name):
        os.unlink(tmp.name)
        return None
    return tmp.name


EXTENSIONS_IMAGE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def decoder_pochette_personnalisee(cover_b64, cover_mime):
    """Décode une image de pochette envoyée en base64 par le front (choisie
    par l'utilisateur) et la reconvertit en jpeg 500px (même format que
    extraire_pochette, pour un codec attached_pic compatible partout) ;
    None si invalide."""
    ext = EXTENSIONS_IMAGE.get(cover_mime)
    if not ext:
        return None
    try:
        brut = base64.b64decode(cover_b64, validate=True)
    except (ValueError, TypeError):
        return None
    if not brut:
        return None
    src = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    src.write(brut)
    src.close()
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    resolution = CONFIG.get("pochette_resolution", 500)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", src.name,
             "-frames:v", "1", "-vf", f"scale={resolution}:-2", tmp.name],
            capture_output=True)
    except OSError:
        os.unlink(tmp.name)
        raise
    finally:
        os.unlink(src.name)
    if not os.path.getsize(tmp.name):
        os.unlink(tmp.name)
        return None
    return tmp.name


@app.post("/api/audio/extract")
def extraire_audio():
    data = request.json or {}
    source = fichier_video_valide(data.get("file", ""))
    fmt_id = data.get("format", "mp3")
    fmt = AUDIO_FORMATS.get(fmt_id)
    if not source or not fmt:
        return jsonify({"error": "Fichier ou format invalide"}), 400
    cover_b64 = data.get("cover_b64")
    cover_mime = data.get("cover_mime")
    if cover_b64 and cover_mime not in EXTENSIONS_IMAGE:
        return jsonify({"error": "Format d'image de pochette non supporté"}), 400
    task_id = new_task("audio")
    duree = duree_video(source)

    def travail():
        os.makedirs(AUDIO_DIR, exist_ok=True)
        nom = os.path.splitext(os.path.basename(source))[0]
        sortie = chemin_sans_ecrasement(
            os.path.join(AUDIO_DIR, f"{nom}.{fmt['ext']}"))
        pochette = None
        if fmt_id in FORMATS_POCHETTE:
            if cover_b64:
                pochette = decoder_pochette_personnalisee(cover_b64, cover_mime)
            elif duree and CONFIG.get("pochette_auto", True):
                pochette = extraire_pochette(source, duree)
        try:
            if pochette:
                args = ["-i", source, "-i", pochette,
                        "-map", "0:a", "-map", "1:0",
                        "-c:v", "copy", "-disposition:v", "attached_pic"] \
                       + fmt["args"] + ["-metadata", f"title={nom}"]
                if fmt_id == "mp3":
                    args += ["-id3v2_version", "3",
                             "-metadata:s:v", "title=Album cover",
                             "-metadata:s:v", "comment=Cover (front)"]
            else:
                args = ["-i", source, "-vn", "-map", "a"] + fmt["args"] \
                       + ["-metadata", f"title={nom}"]
            if lancer_ffmpeg(task_id, args, sortie, duree):
                terminer(task_id, sortie)
        finally:
            if pochette:
                os.unlink(pochette)

    soumettre_encodage(task_id, travail)
    return jsonify({"task_id": task_id})


@app.post("/api/cut")
def decouper():
    data = request.json or {}
    source = fichier_video_valide(data.get("file", ""))
    if not source:
        return jsonify({"error": "Fichier introuvable"}), 400
    try:
        t1, t2 = float(data.get("t1")), float(data.get("t2"))
    except (TypeError, ValueError):
        return jsonify({"error": "t1/t2 invalides"}), 400
    duree = duree_video(source)
    if t2 <= t1 or t1 < 0 or (duree and t1 >= duree):
        return jsonify({"error": "Intervalle invalide (t2 doit être > t1, "
                                  "dans les bornes de la vidéo)"}), 400
    if duree and t2 > duree:
        t2 = duree
    task_id = new_task("cut")

    def travail():
        q = _qualite_video()
        etiquette = f"{t1 / 60:g}m-{t2 / 60:g}m".replace(".", "_")
        sortie = chemin_sans_ecrasement(
            f"{os.path.splitext(source)[0]}_extrait_{etiquette}.mp4")
        # Ré-encodage (pas de -c copy) pour une coupe précise hors images clés.
        if lancer_ffmpeg(task_id, [
            "-ss", f"{t1:.3f}", "-to", f"{t2:.3f}", "-i", source,
            "-c:v", "libx264", "-crf", str(q["crf"]), "-preset", q["preset"],
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", f"{q['audio_kbps']}k",
            "-movflags", "+faststart",
        ], sortie, t2 - t1):
            terminer(task_id, sortie)

    soumettre_encodage(task_id, travail)
    return jsonify({"task_id": task_id})


@app.post("/api/tasks/<task_id>/stop")
def arreter_tache(task_id):
    with TASKS_LOCK:
        tache = TASKS.get(task_id)
        proc = PROCS.get(task_id)
        if tache and tache["status"] == "running":
            tache["stopping"] = True
    if not tache:
        abort(404)
    if proc:
        proc.terminate()
    return jsonify({"ok": True})


# ------------------------------------------------------- miniatures timeline

MINIATURES_DIR = os.path.join(DOWNLOADS_DIR, ".miniatures")


@app.post("/api/thumbnails")
def miniatures_timeline():
    """Génère (et met en cache) la bande de miniatures d'une vidéo."""
    import hashlib
    source = fichier_video_valide((request.json or {}).get("file", ""))
    if not source:
        return jsonify({"error": "Fichier introuvable"}), 400
    duree = duree_video(source)
    if not duree:
        return jsonify({"error": "Durée illisible"}), 400
    nb_miniatures = CONFIG.get("nb_miniatures", 16)
    # nb_miniatures dans la clé de cache : un changement du réglage doit
    # regénérer la bande plutôt que de resservir un cache figé sur l'ancien
    # nombre d'images.
    cle = f"{os.path.basename(source)}:{os.path.getmtime(source)}:{nb_miniatures}"
    h = hashlib.md5(cle.encode()).hexdigest()[:16]
    dossier = os.path.join(MINIATURES_DIR, h)
    if not os.path.isdir(dossier) or not os.listdir(dossier):
        os.makedirs(dossier, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", source,
             "-vf", f"fps={nb_miniatures}/{duree},scale=160:-2",
             "-frames:v", str(nb_miniatures),
             os.path.join(dossier, "t_%02d.jpg")],
            capture_output=True)
    nb = len([f for f in os.listdir(dossier) if f.endswith(".jpg")])
    return jsonify({"hash": h, "count": nb, "duration": duree})


@app.get("/api/thumb/<h>/<int:i>")
def servir_miniature(h, i):
    if not re.fullmatch(r"[0-9a-f]{16}", h):
        abort(404)
    return send_from_directory(os.path.join(MINIATURES_DIR, h), f"t_{i:02d}.jpg")


@app.get("/api/poster/<dossier>/<path:nom>")
def poster_fichier(dossier, nom):
    """Vignette unique pour la bibliothèque (cache dans .miniatures).

    video : image prise à 10 % de la durée ; audio : pochette embarquée
    s'il y en a une, sinon 404 et le front garde son icône."""
    import hashlib
    racine = {"video": DOWNLOADS_DIR, "audio": AUDIO_DIR}.get(dossier)
    if not racine:
        abort(404)
    chemin = os.path.normpath(os.path.join(racine, nom))
    if not chemin.startswith(racine + os.sep) or not os.path.isfile(chemin):
        abort(404)
    cle = f"poster:{dossier}:{nom}:{os.path.getmtime(chemin)}"
    h = hashlib.md5(cle.encode()).hexdigest()[:16]
    os.makedirs(MINIATURES_DIR, exist_ok=True)
    cache = os.path.join(MINIATURES_DIR, f"p_{h}.jpg")
    if not os.path.isfile(cache):
        if dossier == "video":
            duree = duree_video(chemin) or 0
            args = ["-ss", f"{duree * 0.1:.2f}", "-i", chemin]
        else:
            args = ["-i", chemin, "-an"]
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error"] + args +
            ["-frames:v", "1", "-vf", "scale=112:-2", cache],
            capture_output=True)
        if not os.path.isfile(cache) or os.path.getsize(cache) == 0:
            if os.path.isfile(cache):
                os.remove(cache)
            abort(404)
    return send_from_directory(MINIATURES_DIR, f"p_{h}.jpg")


# ------------------------------------------------------------- radio

@app.get("/api/radio/stations")
def stations_radio():
    return jsonify(RADIO_STATIONS)


@app.get("/api/radio/search")
def rechercher_radio():
    """Recherche de stations dans l'annuaire ouvert Radio Browser.

    Proxifié côté serveur pour choisir le miroir et uniformiser le format
    avec RADIO_STATIONS ({name, genre, url})."""
    import json as jsonlib
    import urllib.parse
    import urllib.request
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"error": "Requête trop courte"}), 400
    api = ("https://all.api.radio-browser.info/json/stations/search?"
           + urllib.parse.urlencode({
               "name": q, "limit": 30, "hidebroken": "true",
               "order": "clickcount", "reverse": "true"}))
    try:
        req = urllib.request.Request(api, headers={"User-Agent": "VideoCoder/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            stations = jsonlib.load(resp)
    except Exception as e:
        return jsonify({"error": f"Annuaire injoignable : {e}"}), 502
    vues, resultats = set(), []
    for s in stations:
        url = (s.get("url_resolved") or s.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or url in vues:
            continue
        vues.add(url)
        genre = ", ".join(filter(None, [
            (s.get("tags") or "").split(",")[0].strip(),
            s.get("country") or None,
            f"{s['bitrate']} kb/s" if s.get("bitrate") else None]))
        resultats.append({"name": (s.get("name") or "Station").strip(),
                          "genre": genre, "url": url})
    return jsonify(resultats)


@app.get("/api/radio/nowplaying")
def radio_nowplaying():
    """Infos du flux (nom, genre, titre en cours) via les métadonnées ICY."""
    import urllib.request
    url = request.args.get("url", "")
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL invalide"}), 400
    try:
        req = urllib.request.Request(url, headers={"Icy-MetaData": "1",
                                                   "User-Agent": "VideoCoder/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            infos = {
                "station": resp.headers.get("icy-name"),
                "genre": resp.headers.get("icy-genre"),
                "bitrate": resp.headers.get("icy-br"),
                "title": None,
            }
            metaint = resp.headers.get("icy-metaint")
            if metaint:
                resp.read(int(metaint))
                taille = ord(resp.read(1)) * 16
                if taille:
                    bloc = resp.read(taille).decode("utf-8", "ignore")
                    m = re.search(r"StreamTitle='([^;]*)';", bloc)
                    if m:
                        infos["title"] = m.group(1).strip() or None
        return jsonify(infos)
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.post("/api/radio/record")
def enregistrer_radio():
    data = request.json or {}
    url = data.get("url", "").strip()
    nom = re.sub(r"[^\w\-]+", "_", data.get("name", "radio")).strip("_") or "radio"
    try:
        minutes = float(data.get("minutes", 10))
    except (TypeError, ValueError):
        return jsonify({"error": "Durée invalide"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL de flux invalide"}), 400
    if not 0 < minutes <= 240:
        return jsonify({"error": "Durée entre 1 min et 4 h"}), 400
    task_id = new_task("radio")
    secondes = minutes * 60

    def travail():
        from datetime import datetime
        os.makedirs(AUDIO_DIR, exist_ok=True)
        horodatage = datetime.now().strftime("%Y-%m-%d_%Hh%M")
        sortie = chemin_sans_ecrasement(
            os.path.join(AUDIO_DIR, f"{nom}_{horodatage}.mp3"))
        if lancer_ffmpeg(task_id, [
            "-i", url, "-t", f"{secondes:.0f}",
            "-c:a", "libmp3lame", "-b:a", "128k",
        ], sortie, secondes):
            terminer(task_id, sortie)

    threading.Thread(target=travail, daemon=True).start()
    return jsonify({"task_id": task_id})


# ------------------------------------------------------------- images

@app.post("/api/frames")
def extraire_images():
    import shutil as sh
    data = request.json or {}
    source = fichier_video_valide(data.get("file", ""))
    fmt = data.get("format", "jpg")
    try:
        intervalle = float(data.get("every", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Intervalle invalide"}), 400
    if not source or fmt not in ("jpg", "png") or not 0.04 <= intervalle <= 3600:
        return jsonify({"error": "Paramètres invalides"}), 400
    duree = duree_video(source)
    task_id = new_task("frames")

    def travail():
        base = os.path.splitext(source)[0] + "_images"
        dossier = base + "_tmp"
        os.makedirs(dossier, exist_ok=True)
        ok = lancer_ffmpeg(task_id, [
            "-i", source, "-vf", f"fps=1/{intervalle}", "-vsync", "vfr",
        ] + (["-q:v", "2"] if fmt == "jpg" else []),
            os.path.join(dossier, f"image_%04d.{fmt}"), duree)
        if ok:
            nb = len(os.listdir(dossier))
            zip_path = chemin_sans_ecrasement(base + ".zip")
            sh.make_archive(zip_path[:-4], "zip", dossier)
            sh.rmtree(dossier)
            terminer(task_id, zip_path,
                     [f"{nb} images {fmt} (1 toutes les {intervalle:g} s)"])
        else:
            sh.rmtree(dossier, ignore_errors=True)

    soumettre_encodage(task_id, travail)
    return jsonify({"task_id": task_id})


# ------------------------------------------------------------- musique

@app.post("/api/music")
def bande_musicale():
    data = request.json or {}
    video = fichier_video_valide(data.get("video", ""))
    audio = os.path.normpath(os.path.join(AUDIO_DIR, data.get("audio", "")))
    mode = data.get("mode", "replace")
    if not video or mode not in ("replace", "mix") \
            or not audio.startswith(AUDIO_DIR + os.sep) or not os.path.isfile(audio):
        return jsonify({"error": "Paramètres invalides"}), 400
    duree = duree_video(video)
    task_id = new_task("music")

    def travail():
        # Pas de -crf/-preset ici : -c:v copy, aucun ré-encodage vidéo.
        audio_kbps = _qualite_video()["audio_kbps"]
        sortie = chemin_sans_ecrasement(
            os.path.splitext(video)[0] + "_musique.mp4")
        if mode == "replace":
            args = ["-i", video, "-i", audio,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy"]
        else:
            args = ["-i", video, "-i", audio,
                    "-filter_complex",
                    "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2",
                    "-map", "0:v", "-c:v", "copy"]
        args += ["-c:a", "aac", "-b:a", f"{audio_kbps}k", "-shortest",
                 "-movflags", "+faststart"]
        if lancer_ffmpeg(task_id, args, sortie, duree):
            terminer(task_id, sortie)

    soumettre_encodage(task_id, travail)
    return jsonify({"task_id": task_id})


# ------------------------------------------------------------- texte

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


@app.post("/api/text")
def incruster_texte():
    import tempfile
    data = request.json or {}
    source = fichier_video_valide(data.get("file", ""))
    texte = (data.get("text") or "").strip()
    position = data.get("position", "bottom")
    couleur = data.get("color", "white")
    if not source or not texte or position not in ("top", "center", "bottom") \
            or not re.fullmatch(r"[#0-9a-zA-Z]+", couleur):
        return jsonify({"error": "Paramètres invalides"}), 400
    duree = duree_video(source)
    task_id = new_task("text")

    def travail():
        # Pas d'audio_kbps ici : -c:a copy, aucun ré-encodage audio.
        q = _qualite_video()
        # textfile= évite tout échappement du texte dans le filtre drawtext
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(texte)
            fichier_texte = f.name
        y = {"top": "h*0.06", "center": "(h-text_h)/2",
             "bottom": "h-text_h-h*0.06"}[position]
        filtre = (f"drawtext=fontfile={FONT_BOLD}:textfile={fichier_texte}:"
                  f"fontsize=h/14:fontcolor={couleur}:borderw=3:bordercolor=black@0.7:"
                  f"x=(w-text_w)/2:y={y}")
        sortie = chemin_sans_ecrasement(
            os.path.splitext(source)[0] + "_titre.mp4")
        ok = lancer_ffmpeg(task_id, [
            "-i", source, "-vf", filtre,
            "-c:v", "libx264", "-crf", str(q["crf"]), "-preset", q["preset"],
            "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart",
        ], sortie, duree)
        os.unlink(fichier_texte)
        if ok:
            terminer(task_id, sortie)

    soumettre_encodage(task_id, travail)
    return jsonify({"task_id": task_id})


# Transitions xfade proposées pour l'effet d'intro/outro
EFFETS_XFADE = {
    "fadeblack": "Fondu noir",
    "fadewhite": "Fondu blanc",
    "circleopen": "Cercle qui s'ouvre",
    "wiperight": "Balayage",
    "slideright": "Glissement",
    "zoomin": "Zoom",
    "pixelize": "Pixellisation",
    "hblur": "Flou",
    "dissolve": "Dissolution",
    "radial": "Volet radial",
}


def infos_flux(chemin):
    """(largeur, hauteur, fps, a_du_son) du premier flux vidéo, ou None."""
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "csv=p=0", chemin],
        capture_output=True, text=True)
    try:
        w, h, fps = res.stdout.strip().splitlines()[0].split(",")[:3]
        audio = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", chemin],
            capture_output=True, text=True).stdout.strip() != ""
        return int(w), int(h), fps, audio
    except (ValueError, IndexError):
        return None


@app.get("/api/effects")
def liste_effets():
    return jsonify([{"id": k, "label": v} for k, v in EFFETS_XFADE.items()])


@app.post("/api/effects")
def effet_video():
    data = request.json or {}
    source = fichier_video_valide(data.get("file", ""))
    effet = data.get("effect", "fadeblack")
    ou = data.get("where", "intro")
    try:
        d = float(data.get("duration", 2))
    except (TypeError, ValueError):
        return jsonify({"error": "Durée invalide"}), 400
    if not source or effet not in EFFETS_XFADE \
            or ou not in ("intro", "outro", "both"):
        return jsonify({"error": "Paramètres invalides"}), 400
    duree = duree_video(source)
    infos = infos_flux(source)
    if not duree or not infos:
        return jsonify({"error": "Vidéo illisible"}), 400
    d = max(0.5, min(d, 5.0, duree / 2 - 0.1))
    task_id = new_task("effects")

    def travail():
        q = _qualite_video()
        w, h, fps, audio = infos
        # L'effet est un xfade entre un carton noir et la vidéo (et/ou l'inverse
        # en fin) : toutes les transitions xfade deviennent des effets d'intro.
        # settb=AVTB : xfade exige des bases de temps identiques sur ses entrées
        noir = (f"color=c=black:s={w}x{h}:r={fps}:d={d + 0.2:.3f},"
                f"setsar=1,settb=AVTB")
        # fps avant settb : le filtre fps réécrirait la base de temps après coup
        fv, fa = [f"[0:v]setsar=1,fps={fps},settb=AVTB[v0]"], []
        etape = "[v0]"
        if ou in ("intro", "both"):
            fv.append(f"{noir}[ci];[ci]{etape}xfade=transition={effet}:"
                      f"duration={d}:offset=0[v1]")
            etape = "[v1]"
            fa.append(f"afade=t=in:st=0:d={d}")
        if ou in ("outro", "both"):
            fv.append(f"{noir}[co];{etape}[co]xfade=transition={effet}:"
                      f"duration={d}:offset={max(0.0, duree - d):.3f}[v2]")
            etape = "[v2]"
            fa.append(f"afade=t=out:st={max(0.0, duree - d):.3f}:d={d}")
        fv.append(f"{etape}format=yuv420p[vout]")
        graphe = ";".join(fv)
        args = ["-i", source]
        maps = ["-map", "[vout]"]
        if audio:
            graphe += f";[0:a]{','.join(fa)}[aout]"
            maps += ["-map", "[aout]", "-c:a", "aac", "-b:a", f"{q['audio_kbps']}k"]
        sortie = chemin_sans_ecrasement(
            f"{os.path.splitext(source)[0]}_effet_{effet}.mp4")
        if lancer_ffmpeg(task_id, args + ["-filter_complex", graphe] + maps + [
            "-c:v", "libx264", "-crf", str(q["crf"]), "-preset", q["preset"],
            "-movflags", "+faststart",
        ], sortie, duree):
            terminer(task_id, sortie)

    soumettre_encodage(task_id, travail)
    return jsonify({"task_id": task_id})


# ------------------------------------------------------------------ medley

TRANSITIONS_MEDLEY = {
    "fade": "Fondu enchaîné",
    "slideleft": "Glissement ←",
    "slideright": "Glissement →",
    "wipeleft": "Volet ←",
    "wiperight": "Volet →",
    "circleopen": "Cercle ouvrant",
    "circleclose": "Cercle fermant",
    "radial": "Radial",
    "dissolve": "Dissolution",
}
RESOLUTIONS_MEDLEY = {"480p": (854, 480), "720p": (1280, 720),
                      "1080p": (1920, 1080)}
DEBITS_MEDLEY = {  # kb/s vidéo par résolution ; "auto" = CRF 22
    "low": {"480p": 800, "720p": 1500, "1080p": 3000},
    "medium": {"480p": 1500, "720p": 3000, "1080p": 6000},
    "high": {"480p": 2500, "720p": 5000, "1080p": 10000},
}
APERCU_MEDLEY = "medley_preview.mp4"        # dans MINIATURES_DIR, écrasé


@app.get("/api/medley/transitions")
def transitions_medley():
    return jsonify([{"id": k, "label": v} for k, v in TRANSITIONS_MEDLEY.items()])


@app.get("/api/medley/preview")
def apercu_medley():
    if not os.path.isfile(os.path.join(MINIATURES_DIR, APERCU_MEDLEY)):
        abort(404)
    return send_from_directory(MINIATURES_DIR, APERCU_MEDLEY, conditional=True)


@app.post("/api/medley")
def creer_medley():
    data = request.json or {}
    apercu = bool(data.get("preview"))
    clips_in = data.get("clips") or []
    trans_in = data.get("transitions") or []
    resolution = data.get("resolution", "720p")
    debit = data.get("bitrate", "auto")
    if not 2 <= len(clips_in) <= 12:
        return jsonify({"error": "Le medley demande de 2 à 12 clips"}), 400
    if len(trans_in) != len(clips_in) - 1:
        return jsonify({"error": "Il faut une transition entre chaque clip"}), 400
    if resolution not in RESOLUTIONS_MEDLEY or \
            debit not in ("auto", *DEBITS_MEDLEY):
        return jsonify({"error": "Résolution ou débit invalide"}), 400

    clips = []
    for c in clips_in:
        chemin = fichier_video_valide(c.get("file", ""))
        if not chemin:
            return jsonify({"error": f"Fichier introuvable : {c.get('file')}"}), 400
        infos = infos_flux(chemin)
        duree = duree_video(chemin)
        if not infos or not duree:
            return jsonify({"error": f"Vidéo illisible : {c.get('file')}"}), 400
        try:
            t1 = max(0.0, float(c.get("t1", 0)))
            t2 = min(float(c.get("t2", duree)), duree)
        except (TypeError, ValueError):
            return jsonify({"error": "t1/t2 invalides"}), 400
        ext = t2 - t1
        if ext < 1:
            return jsonify({"error": "Chaque extrait doit durer au moins 1 s"}), 400
        if apercu:                        # aperçu : 5 premières secondes max
            ext = min(ext, 5.0)
        clips.append({"chemin": chemin, "t1": t1, "ext": ext,
                      "audio": infos[3]})

    transitions = []
    for i, t in enumerate(trans_in):
        typ = t.get("type", "fade")
        if typ not in TRANSITIONS_MEDLEY:
            return jsonify({"error": f"Transition inconnue : {typ}"}), 400
        try:
            d = max(0.5, min(float(t.get("duration", 1)), 3.0))
        except (TypeError, ValueError):
            return jsonify({"error": "Durée de transition invalide"}), 400
        # Une transition ne peut pas dépasser la moitié des clips adjacents.
        transitions.append(round(max(0.1, min(
            d, clips[i]["ext"] / 2, clips[i + 1]["ext"] / 2)), 3))
    types = [t.get("type", "fade") for t in trans_in]
    duree_totale = sum(c["ext"] for c in clips) - sum(transitions)
    task_id = new_task("medley")

    def travail():
        w, h = (640, 360) if apercu else RESOLUTIONS_MEDLEY[resolution]
        args, fv = [], []
        for i, c in enumerate(clips):
            args += ["-ss", f"{c['t1']:.3f}", "-t", f"{c['ext']:.3f}",
                     "-i", c["chemin"]]
            fv.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                      f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                      f"fps=30,setsar=1,settb=AVTB,format=yuv420p[v{i}]")
            if c["audio"]:
                fv.append(f"[{i}:a]aformat=sample_rates=44100:"
                          f"channel_layouts=stereo[a{i}]")
            else:                        # clip muet : piste de silence
                fv.append(f"anullsrc=r=44100:cl=stereo:d={c['ext']:.3f}[a{i}]")
        va, aa, offset = "[v0]", "[a0]", clips[0]["ext"]
        for i, d in enumerate(transitions):
            offset -= d
            dern = i == len(transitions) - 1
            outv, outa = ("[vout]", "[aout]") if dern else (f"[x{i}]", f"[y{i}]")
            fv.append(f"{va}[v{i + 1}]xfade=transition={types[i]}:"
                      f"duration={d}:offset={offset:.3f}{outv}")
            fv.append(f"{aa}[a{i + 1}]acrossfade=d={d}{outa}")
            va, aa = outv, outa
            offset += clips[i + 1]["ext"]
        if apercu:
            # Aperçu : volontairement exclu du réglage qualité global —
            # doit rester rapide par construction, jamais affecté.
            enc = ["-c:v", "libx264", "-crf", "30", "-preset", "ultrafast"]
            audio_kbps = 128
            os.makedirs(MINIATURES_DIR, exist_ok=True)
            sortie = os.path.join(MINIATURES_DIR, APERCU_MEDLEY)
        else:
            q = _qualite_video()
            audio_kbps = q["audio_kbps"]
            if debit == "auto":
                enc = ["-c:v", "libx264", "-crf", str(q["crf"]), "-preset", q["preset"]]
            else:
                # Mode bitrate (résolution/débit choisis par tâche) : pas de
                # -crf (incompatible avec -b:v), seul le preset s'applique.
                k = DEBITS_MEDLEY[debit][resolution]
                enc = ["-c:v", "libx264", "-b:v", f"{k}k",
                       "-maxrate", f"{int(k * 1.5)}k", "-bufsize", f"{k * 3}k",
                       "-preset", q["preset"]]
            sortie = chemin_sans_ecrasement(
                os.path.join(DOWNLOADS_DIR, f"medley_{len(clips)}clips.mp4"))
        if lancer_ffmpeg(task_id, args + [
            "-filter_complex", ";".join(fv), "-map", "[vout]", "-map", "[aout]",
        ] + enc + ["-c:a", "aac", "-b:a", f"{audio_kbps}k", "-movflags", "+faststart"],
                sortie, duree_totale):
            if apercu:
                update_task(task_id, status="done", progress=100,
                            message="Aperçu prêt",
                            output={"name": "Aperçu du medley",
                                    "size": os.path.getsize(sortie),
                                    "type": "preview", "warnings": []})
            else:
                terminer(task_id, sortie)

    soumettre_encodage(task_id, travail)
    return jsonify({"task_id": task_id})


if __name__ == "__main__":
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 5000)),
            debug=False, threaded=True)
