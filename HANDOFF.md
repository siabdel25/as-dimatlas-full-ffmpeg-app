# HANDOFF — VideoCoder Studio

État du projet pour reprise en main (par vous, ou par une future session
d'assistant). Écrit le 2026-07-05.

## 1. État du dépôt

- **Branche `main`** : contient tout, y compris le merge de `dev`. **4 commits
  d'avance sur `origin/main`** — le push a échoué (403, identifiants GitHub
  en cache pour un compte `Siabdel` sans droit d'écriture sur
  `siabdel25/as-dimatlas-full-ffmpeg-app`). À pousser vous-même :
  ```bash
  git push origin main
  ```
  Si le 403 persiste, corrigez les identifiants cache (`git credential-cache
  exit` ou `gh auth login`) avant de réessayer.
- **Branche `dev`** : déjà poussée sur GitHub, contient les mêmes commits
  (medley + recherche) avant le merge. Peut être supprimée après le push de
  `main` si vous ne comptez pas continuer à développer dessus.
- Working tree propre au moment de l'écriture de ce document.
- Deux fichiers legacy présents à la racine, jamais nettoyés : `scrap_movie.py.old`
  et `yt_scraper.py`. Ni l'un ni l'autre n'est utilisé par l'app web ;
  `scrap_movie.py` (sans `.old`) est la version CLI maintenue. À supprimer
  si vous confirmez qu'ils sont obsolètes.

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

Documentation utilisateur : voir **`MANUEL-UTILISATEUR.md`** (à la racine).

## 3. Architecture en un coup d'œil

```
app.py                  API Flask, tâches de fond, file d'encodage
static/index.html       coquille SPA (sidebar, thème)
static/app.js           tous les composants/vues Vue 3 (un seul fichier)
static/app.css           design system (tokens --vc-*, dark/light)
docs/FAISABILITE-MEDLEY.md   étude de faisabilité du medley (référence technique)
scrap_movie.py           CLI à menu, indépendante de l'app web
Dockerfile, docker-compose.yml   déploiement local
```

Chaque opération lourde suit le même schéma :
`POST /api/xxx` → `new_task()`/`soumettre_encodage()` → thread ou file
d'encodage → `lancer_ffmpeg()` publie la progression → `GET
/api/tasks/<id>` interrogé par `TaskProgress` (front) toutes les 800 ms.

## 4. Points d'attention pour la suite

- **`ENCODE_QUEUE`** limite à 2 encodages ffmpeg simultanés
  (`ENCODERS` env var). Les tâches réseau (YouTube, radio) ne passent pas
  par cette file — elles restent en threads directs.
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
- **Push GitHub** : le compte configuré en cache (`Siabdel`) n'a pas les
  droits d'écriture sur ce dépôt. Un assistant ne peut pas contourner ce
  refus (bloqué par la politique d'action de l'agent) — c'est normal et
  volontaire, il faut pousser depuis votre propre session.

## 5. Suggestions naturelles pour la prochaine itération

Non demandées, juste des pistes issues du travail en cours :

- Upload de fichiers externes (hors `downloads/`) pour le Medley, si vous
  voulez importer des vidéos qui ne sont pas déjà dans la bibliothèque.
- Transitions vidéo entre deux vidéos indépendantes (mentionné dans une
  spec initiale coupée) — même mécanisme xfade que les Effets/Medley.
- Nettoyage périodique de `downloads/.miniatures/` si le volume devient
  gênant.
