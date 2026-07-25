#!/usr/bin/env python3
"""
scrap_movie.py — Boîte à outils vidéo avec menu interactif.

    1. Télécharger une vidéo YouTube          (yt-dlp -> downloads/)
    2. Convertir pour WhatsApp / Instagram    (H.264 + AAC, < 16 Mo)
    3. Extraire l'audio                       (mp3, aac, wav, ogg, flac -> audio/)
    4. Découper une vidéo de t1 à t2 minutes

Dépendances : yt-dlp (pip) et ffmpeg/ffprobe (système).
"""

import os
import re
import shutil
import subprocess
import sys

DOWNLOADS_DIR = "downloads"
AUDIO_DIR = "audio"
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v")

AUDIO_FORMATS = {
    "mp3":  {"ext": "mp3",  "args": ["-c:a", "libmp3lame", "-b:a", "192k"]},
    "aac":  {"ext": "m4a",  "args": ["-c:a", "aac", "-b:a", "192k"]},
    "ogg":  {"ext": "ogg",  "args": ["-c:a", "libvorbis", "-q:a", "5"]},
    "wav":  {"ext": "wav",  "args": ["-c:a", "pcm_s16le"]},
    "flac": {"ext": "flac", "args": ["-c:a", "flac"]},
}


# ---------------------------------------------------------------- utilitaires

def taille_lisible(octets):
    for unite in ("o", "Ko", "Mo", "Go"):
        if octets < 1024 or unite == "Go":
            return f"{octets:.1f} {unite}" if unite != "o" else f"{octets} o"
        octets /= 1024


def chemin_sans_ecrasement(chemin):
    """Retourne un chemin libre en suffixant _1, _2… si le fichier existe."""
    if not os.path.exists(chemin):
        return chemin
    base, ext = os.path.splitext(chemin)
    n = 1
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def duree_video(chemin):
    """Durée en secondes via ffprobe, ou None en cas d'échec."""
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", chemin],
        capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return None


def lancer_ffmpeg(args, sortie):
    """Exécute ffmpeg ; retourne True si OK, sinon affiche l'erreur."""
    cmd = ["ffmpeg", "-hide_banner", "-y"] + args + [sortie]
    print("\n⏳ Encodage en cours…")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("❌ Erreur ffmpeg :")
        print("\n".join(res.stderr.splitlines()[-6:]))
        return False
    taille = os.path.getsize(sortie)
    print(f"✅ Fichier créé : {sortie} ({taille_lisible(taille)})")
    return True


def lire_temps_minutes(invite):
    """Lit un temps en minutes : accepte 2, 1.5 ou mm:ss. Retourne des secondes."""
    while True:
        saisie = input(invite).strip().replace(",", ".")
        m = re.fullmatch(r"(\d+):([0-5]?\d)", saisie)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        try:
            return float(saisie) * 60
        except ValueError:
            print("  Format invalide. Exemples : 2  |  1.5  |  2:30")


def choisir_fichier():
    """Liste les vidéos de downloads/ et laisse choisir, ou saisir un chemin."""
    videos = []
    if os.path.isdir(DOWNLOADS_DIR):
        videos = sorted(
            f for f in os.listdir(DOWNLOADS_DIR)
            if f.lower().endswith(VIDEO_EXTS))
    if videos:
        print(f"\nVidéos dans {DOWNLOADS_DIR}/ :")
        for i, nom in enumerate(videos, 1):
            taille = os.path.getsize(os.path.join(DOWNLOADS_DIR, nom))
            print(f"  {i}. {nom} ({taille_lisible(taille)})")
        print("  0. Saisir un autre chemin")
        choix = input("Votre choix : ").strip()
        if choix.isdigit() and 1 <= int(choix) <= len(videos):
            return os.path.join(DOWNLOADS_DIR, videos[int(choix) - 1])
    chemin = input("Chemin du fichier vidéo : ").strip().strip("'\"")
    if not os.path.isfile(chemin):
        print("❌ Fichier introuvable.")
        return None
    return chemin


# -------------------------------------------------------------------- options

def telecharger_youtube():
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        print("❌ Le module 'yt-dlp' n'est pas installé dans cet interpréteur Python.\n"
              "   Installez-le (pip install yt-dlp) ou lancez le script avec le venv "
              "du projet, ex. : .venv/bin/python scrap_movie.py")
        return

    url = input("URL de la vidéo YouTube : ").strip()
    if not url:
        return
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "outtmpl": f"{DOWNLOADS_DIR}/%(title)s.%(ext)s",
        "noplaylist": True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        duree = int(info.get("duration") or 0)
        vues = info.get("view_count")
        print(f"\nTitre    : {info.get('title')}")
        print(f"Chaîne   : {info.get('uploader')}")
        print(f"Durée    : {duree // 60}:{duree % 60:02d}")
        print(f"Vues     : {'inconnu' if vues is None else f'{vues:,}'.replace(',', ' ')}")
        if input("\nTélécharger ? [O/n] : ").strip().lower() in ("", "o", "oui"):
            ydl.download([url])
            print(f"✅ Vidéo téléchargée dans {DOWNLOADS_DIR}/")


def convertir_reseaux_sociaux():
    source = choisir_fichier()
    if not source:
        return
    duree = duree_video(source)
    if not duree:
        print("❌ Impossible de lire la durée de la vidéo.")
        return

    # Débit vidéo visant ~14 Mo au total (audio 96k), borné à [300k, 2000k].
    cible_kbits = 14 * 8192
    debit_video = int(cible_kbits / duree) - 96
    debit_video = max(300, min(debit_video, 2000))

    base = os.path.splitext(source)[0]
    sortie = chemin_sans_ecrasement(f"{base}_whatsapp.mp4")
    ok = lancer_ffmpeg([
        "-i", source,
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p",
        "-b:v", f"{debit_video}k",
        "-maxrate", f"{int(debit_video * 1.2)}k",
        "-bufsize", f"{debit_video * 2}k",
        "-preset", "medium", "-r", "30",
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100",
        "-movflags", "+faststart",
    ], sortie)
    if not ok:
        return
    if os.path.getsize(sortie) > 16 * 1024 * 1024:
        print("⚠️  Le fichier dépasse 16 Mo (limite vidéo WhatsApp).")
    if duree > 90:
        print("⚠️  Durée > 90 s : trop long pour un statut WhatsApp "
              "(OK en message et en Reel Instagram).")


def extraire_audio():
    source = choisir_fichier()
    if not source:
        return
    formats = list(AUDIO_FORMATS)
    print("\nFormat de sortie :")
    for i, f in enumerate(formats, 1):
        print(f"  {i}. {f}" + ("  (défaut)" if f == "mp3" else ""))
    choix = input("Votre choix [1] : ").strip() or "1"
    if not (choix.isdigit() and 1 <= int(choix) <= len(formats)):
        print("❌ Choix invalide.")
        return
    fmt = AUDIO_FORMATS[formats[int(choix) - 1]]

    os.makedirs(AUDIO_DIR, exist_ok=True)
    nom = os.path.splitext(os.path.basename(source))[0]
    sortie = chemin_sans_ecrasement(
        os.path.join(AUDIO_DIR, f"{nom}.{fmt['ext']}"))
    lancer_ffmpeg(["-i", source, "-vn", "-map", "a"] + fmt["args"], sortie)


def decouper_video():
    source = choisir_fichier()
    if not source:
        return
    duree = duree_video(source)
    if duree:
        print(f"Durée de la vidéo : {int(duree // 60)}:{int(duree % 60):02d}")

    t1 = lire_temps_minutes("Début t1 (minutes, ex. 1.5 ou 1:30) : ")
    t2 = lire_temps_minutes("Fin   t2 (minutes, ex. 2.5 ou 2:30) : ")
    if t2 <= t1:
        print("❌ t2 doit être supérieur à t1.")
        return
    if duree and t1 >= duree:
        print("❌ t1 dépasse la durée de la vidéo.")
        return
    if duree and t2 > duree:
        print(f"⚠️  t2 dépasse la fin ; l'extrait ira jusqu'à la fin.")
        t2 = duree

    base = os.path.splitext(source)[0]
    etiquette = f"{t1 / 60:g}m-{t2 / 60:g}m".replace(".", "_")
    sortie = chemin_sans_ecrasement(f"{base}_extrait_{etiquette}.mp4")
    # Ré-encodage (pas de -c copy) pour une coupe précise hors images clés.
    lancer_ffmpeg([
        "-ss", f"{t1:.3f}", "-to", f"{t2:.3f}", "-i", source,
        "-c:v", "libx264", "-crf", "22", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
    ], sortie)


# ----------------------------------------------------------------------- menu

MENU = """
╔══════════════════════════════════════════════╗
║           🎬  SCRAP MOVIE — MENU  🎬          ║
╠══════════════════════════════════════════════╣
║  1. Télécharger une vidéo YouTube            ║
║  2. Convertir pour WhatsApp / Instagram      ║
║  3. Extraire l'audio (mp3, aac, wav, …)      ║
║  4. Découper la vidéo (de t1 à t2 minutes)   ║
║  5. Quitter                                  ║
╚══════════════════════════════════════════════╝"""

ACTIONS = {
    "1": telecharger_youtube,
    "2": convertir_reseaux_sociaux,
    "3": extraire_audio,
    "4": decouper_video,
}


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("❌ ffmpeg/ffprobe introuvables. Installez-les d'abord "
                 "(sudo apt install ffmpeg).")
    while True:
        print(MENU)
        choix = input("Votre choix : ").strip()
        if choix == "5" or choix.lower() in ("q", "quit"):
            print("Au revoir 👋")
            break
        action = ACTIONS.get(choix)
        if not action:
            print("❌ Choix invalide.")
            continue
        try:
            action()
        except KeyboardInterrupt:
            print("\n↩️  Opération annulée, retour au menu.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAu revoir 👋")
