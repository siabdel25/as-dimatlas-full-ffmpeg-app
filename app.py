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

Lancement : .venv/bin/python app.py  →  http://localhost:5000
"""

import os
import re
import subprocess
import threading
import uuid

from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v")

AUDIO_FORMATS = {
    "mp3":  {"ext": "mp3",  "args": ["-c:a", "libmp3lame", "-b:a", "192k"]},
    "aac":  {"ext": "m4a",  "args": ["-c:a", "aac", "-b:a", "192k"]},
    "ogg":  {"ext": "ogg",  "args": ["-c:a", "libvorbis", "-q:a", "5"]},
    "wav":  {"ext": "wav",  "args": ["-c:a", "pcm_s16le"]},
    "flac": {"ext": "flac", "args": ["-c:a", "flac"]},
}

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


def duree_video(chemin):
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", chemin],
        capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return None


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


@app.get("/api/files")
def liste_fichiers():
    videos, audios, exports = [], [], []
    for f in sorted(os.listdir(DOWNLOADS_DIR)) if os.path.isdir(DOWNLOADS_DIR) else []:
        chemin = os.path.join(DOWNLOADS_DIR, f)
        if f.lower().endswith(VIDEO_EXTS):
            videos.append({"name": f, "size": os.path.getsize(chemin),
                           "duration": duree_video(chemin)})
        elif f.lower().endswith(".zip"):
            exports.append({"name": f, "size": os.path.getsize(chemin)})
    for f in sorted(os.listdir(AUDIO_DIR)) if os.path.isdir(AUDIO_DIR) else []:
        chemin = os.path.join(AUDIO_DIR, f)
        if os.path.isfile(chemin):
            audios.append({"name": f, "size": os.path.getsize(chemin)})
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
        debit = max(300, min(int(14 * 8192 / duree) - 96, 2000))
        sortie = chemin_sans_ecrasement(
            os.path.splitext(source)[0] + "_whatsapp.mp4")
        ok = lancer_ffmpeg(task_id, [
            "-i", source,
            "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
            "-pix_fmt", "yuv420p",
            "-b:v", f"{debit}k", "-maxrate", f"{int(debit * 1.2)}k",
            "-bufsize", f"{debit * 2}k",
            "-preset", "medium", "-r", "30",
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

    threading.Thread(target=travail, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.post("/api/audio/extract")
def extraire_audio():
    data = request.json or {}
    source = fichier_video_valide(data.get("file", ""))
    fmt = AUDIO_FORMATS.get(data.get("format", "mp3"))
    if not source or not fmt:
        return jsonify({"error": "Fichier ou format invalide"}), 400
    task_id = new_task("audio")
    duree = duree_video(source)

    def travail():
        os.makedirs(AUDIO_DIR, exist_ok=True)
        nom = os.path.splitext(os.path.basename(source))[0]
        sortie = chemin_sans_ecrasement(
            os.path.join(AUDIO_DIR, f"{nom}.{fmt['ext']}"))
        if lancer_ffmpeg(task_id, ["-i", source, "-vn", "-map", "a"]
                         + fmt["args"], sortie, duree):
            terminer(task_id, sortie)

    threading.Thread(target=travail, daemon=True).start()
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
        etiquette = f"{t1 / 60:g}m-{t2 / 60:g}m".replace(".", "_")
        sortie = chemin_sans_ecrasement(
            f"{os.path.splitext(source)[0]}_extrait_{etiquette}.mp4")
        # Ré-encodage (pas de -c copy) pour une coupe précise hors images clés.
        if lancer_ffmpeg(task_id, [
            "-ss", f"{t1:.3f}", "-to", f"{t2:.3f}", "-i", source,
            "-c:v", "libx264", "-crf", "22", "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
        ], sortie, t2 - t1):
            terminer(task_id, sortie)

    threading.Thread(target=travail, daemon=True).start()
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


# ------------------------------------------------------------- radio

@app.get("/api/radio/stations")
def stations_radio():
    return jsonify(RADIO_STATIONS)


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

    threading.Thread(target=travail, daemon=True).start()
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
        args += ["-c:a", "aac", "-b:a", "192k", "-shortest",
                 "-movflags", "+faststart"]
        if lancer_ffmpeg(task_id, args, sortie, duree):
            terminer(task_id, sortie)

    threading.Thread(target=travail, daemon=True).start()
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
            "-c:v", "libx264", "-crf", "22", "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart",
        ], sortie, duree)
        os.unlink(fichier_texte)
        if ok:
            terminer(task_id, sortie)

    threading.Thread(target=travail, daemon=True).start()
    return jsonify({"task_id": task_id})


if __name__ == "__main__":
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 5000)),
            debug=False, threaded=True)
