# HANDOFF — VideoCoder Studio

État du projet pour reprise en main (par vous, ou par une future session
d'assistant). Écrit le 2026-07-05, mis à jour le 2026-07-13.

## 1. État du dépôt

- **Branche `main`** : à jour avec `origin/main` (dernier commit poussé :
  `db2f47e`). Working tree propre.
- **Push GitHub — résolu** : le problème de 403 mentionné dans une version
  antérieure de ce document venait d'un compte `gh` actif (`Siabdel`) sans
  droit d'écriture sur ce dépôt. Deux comptes sont enregistrés en cache ;
  si le 403 revient, basculer sur le bon compte avant de pousser :
  ```bash
  gh auth switch --user siabdel25
  git push origin main
  ```
- **Branche `dev`** : toujours sur GitHub avec les commits pré-merge
  (medley + recherche). Peut être supprimée si vous ne comptez pas continuer
  à développer dessus — non fait, pas de risque à la laisser.
- Deux fichiers legacy toujours présents à la racine, jamais nettoyés :
  `scrap_movie.py.old` et `yt_scraper.py`. Ni l'un ni l'autre n'est utilisé
  par l'app web ; `scrap_movie.py` (sans `.old`) est la version CLI
  maintenue. Toujours à supprimer si vous confirmez qu'ils sont obsolètes
  — voir `TODO.md`.

## 2. Ce qui a été construit, dans l'ordre

1. **App de base** : Flask (API) + Vue 3 SPA (`static/`), ffmpeg/yt-dlp en
   tâches de fond suivies par `task_id`.
2. **Fonctionnalités cœur** : téléchargement YouTube, conversion
   WhatsApp/Instagram, extraction audio, découpage t1→t2, radio (écoute +
   enregistrement), extraction d'images, bande musicale, incrustation de
   titre.
3. **Timeline de découpage visuelle** : lecteur vidéo + 16 miniatures
   cliquables, marqueurs Début/Fin.
4. **Effets d'intro/outro** : transitions xfade sur un carton noir (fondu,
   cercle, zoom…).
5. **File d'attente d'encodage** : 2 ffmpeg simultanés max (variable
   `ENCODERS`), pour ne pas saturer le CPU si plusieurs tâches sont
   lancées d'affilée.
6. **Radio — recherche et favoris** : annuaire mondial Radio Browser en
   plus des 18 stations marocaines ; favoris en localStorage.
7. **Bibliothèque — vignettes** : image pour chaque vidéo, pochette pour
   chaque audio.
8. **Medley multi-clips** *(branche `dev`, mergée)* : assembler 2 à 12
   extraits en une seule vidéo avec transitions xfade réglables, aperçu
   rapide, export 480p/720p/1080p. Voir `docs/FAISABILITE-MEDLEY.md` pour
   l'étude technique complète (graphe ffmpeg, pièges résolus).
9. **Recherche, index, date** dans toutes les listes de fichiers
   (Découpage, Medley, Images, Bande musicale, Titre, Effets, Extraction
   audio, Bibliothèque) : composant `FilePicker` partagé, tri par date de
   création décroissante.
10. **Pochette audio (cover art)** : extraction automatique d'une image de
    la vidéo (à 10 % de la durée) ou upload d'une image personnalisée,
    embarquée en `attached_pic` pour mp3/aac/flac. Extraction audio en lot
    (sélection multi-fichiers dans `FilePicker`).
11. **Dashboard Paramètres** : onglet dédié pour régler la pochette par
    défaut (auto-extraction ou non, résolution), le nombre d'encodeurs
    ffmpeg simultanés et le nombre de miniatures de la timeline, sans
    éditer le code. Persisté dans `config/config.json` (volume Docker
    dédié). Voir section 3 et 4 ci-dessous pour les détails d'implémentation.
12. **Qualité d'encodage** : réglage qualitatif à 3 paliers nommés (Fichiers
    légers / Équilibré / Qualité maximale, pas de CRF/preset brut exposé)
    dans le dashboard Paramètres, appliqué à Découpage, Titre, Effets et
    Medley (rendu final). Exclu de la Conversion réseaux sociaux (calcul de
    taille <16 Mo) et de l'aperçu rapide du Medley (reste rapide par
    construction).

Documentation utilisateur : voir **`MANUEL-UTILISATEUR.md`** (à la racine).
Installation Docker détaillée (Windows/Linux/macOS) : voir
**`MANUEL-INSTALLATION-DOCKER.md`**.

## 3. Architecture en un coup d'œil

```
app.py                  API Flask, tâches de fond, file d'encodage, CONFIG (settings)
static/index.html       coquille SPA (sidebar, thème)
static/app.js           tous les composants/vues Vue 3 (un seul fichier)
static/app.css           design system (tokens --vc-*, dark/light)
docs/FAISABILITE-MEDLEY.md   étude de faisabilité du medley (référence technique)
scrap_movie.py           CLI à menu, indépendante de l'app web
Dockerfile, docker-compose.yml   déploiement local (volumes downloads/, audio/, config/)
config/config.json       paramètres persistés (dashboard Paramètres), gitignoré
```

Chaque opération lourde suit le même schéma :
`POST /api/xxx` → `new_task()`/`soumettre_encodage()` → thread ou file
d'encodage → `lancer_ffmpeg()` publie la progression → `GET
/api/tasks/<id>` interrogé par `TaskProgress` (front) toutes les 800 ms.

## 4. Points d'attention pour la suite

- **`ENCODE_QUEUE`** limite les encodages ffmpeg simultanés (2 par défaut,
  réglable — voir `NB_ENCODEURS` ci-dessous). Les tâches réseau (YouTube,
  radio) ne passent pas par cette file — elles restent en threads directs.
- **Traversée de chemin** : toujours utiliser `fichier_video_valide()` /
  la même logique pour tout nouvel endpoint qui reçoit un nom de fichier
  du client.
- **xfade** (Effets et Medley) exige des entrées de même taille, fps ET
  base de temps → toujours `scale+pad+fps+setsar+settb=AVTB`, avec `fps=`
  *avant* `settb=` dans la chaîne de filtres (sinon `fps` réécrit la
  timebase et xfade échoue avec `-22 Invalid argument`).
- **Miniatures** (`downloads/.miniatures/`) : cache par hash — vignettes
  timeline (`md5(nom:mtime)`), posters bibliothèque (`p_<hash>.jpg`),
  aperçu medley (fichier unique écrasé). Ce dossier n'est jamais nettoyé
  automatiquement ; il grossit avec l'usage. Pas de souci de volume vu
  l'usage local, mais à garder en tête si l'app évolue.
- **Radio Browser** (`/api/radio/search`) dépend d'un service tiers
  externe (`all.api.radio-browser.info`) : pas de clé requise, mais pas de
  garantie de disponibilité — le code gère déjà l'échec proprement (message
  "Aucune station trouvée").
- **Push GitHub** : voir section 1 — `gh auth switch --user siabdel25` si le
  403 revient.
- **Paramètres (`CONFIG`)** : dict module-level chargé une fois au démarrage
  (`_charger_config()`), fusionné sur `CONFIG_DEFAULTS`, jamais remplacé
  brutalement. Un `config.json` absent ou corrompu retombe silencieusement
  sur les défauts — ne JAMAIS laisser une exception de chargement remonter
  jusqu'à l'import du module (panne totale sinon). Écriture protégée par
  `CONFIG_LOCK` + fichier temporaire + `os.replace()` (atomique).
- **`NB_ENCODEURS` : lu une seule fois au démarrage** (précédence
  `config.json` > env `ENCODERS` > défaut 2) pour lancer les threads
  workers — un changement via l'UI Paramètres met à jour la valeur
  "configurée" mais ne relance pas les threads déjà démarrés ("active").
  `GET /api/settings` expose les deux ; un vrai changement effectif
  nécessite `docker compose restart videocoder`.
- **Miniatures timeline** : la clé de cache (`.miniatures/<hash>/`) inclut
  maintenant `nb_miniatures` — un changement du réglage régénère la bande
  au lieu de resservir un cache figé sur l'ancien nombre d'images.
- **`QUALITES_VIDEO` (crf/preset/audio_kbps)** : table à 3 clés
  (`leger`/`equilibre`/`max`), lue via `_qualite_video()` au call-time (pas
  au chargement du module) — une valeur invalide dans `config.json` ne
  peut donc jamais casser un export, contrairement au piège déjà rencontré
  sur `NB_ENCODEURS`. Périmètre d'application asymétrique, à respecter pour
  tout nouvel outil ffmpeg :
  - `preset` : partout où x264 encode, y compris Conversion réseaux
    sociaux et la branche débit explicite du Medley (orthogonal au mode
    bitrate).
  - `crf` : uniquement les sites en mode CRF (Découpage, Titre, Effets,
    Medley auto) — jamais avec `-b:v` (mode bitrate incompatible).
  - `audio_kbps` : sites qui ré-encodent l'audio sans contrainte de taille
    externe. Exclu de Conversion réseaux sociaux (débit audio déjà compté
    dans le calcul du budget `<16 Mo` — le changer sans recalculer ce
    budget romprait la garantie de taille) et de l'aperçu Medley (reste en
    dur, rapide par construction).

## 5. Prochaine itération

Voir **`TODO.md`** (à la racine) pour la liste à jour des pistes
d'évolution, avec contexte et priorité indicative.
