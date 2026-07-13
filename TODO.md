# TODO — VideoCoder Studio

Pistes d'évolution connues, avec contexte pour ne pas avoir à le
redécouvrir. Mis à jour le 2026-07-13 (v2, extension qualité vidéo). Voir
`HANDOFF.md` pour l'état général du dépôt.

## Priorité probable

- **Panneau Stockage / purge de `downloads/.miniatures/`.**
  Le cache de miniatures (vignettes timeline, posters bibliothèque, aperçu
  medley) n'est jamais nettoyé automatiquement et grossit avec l'usage —
  déjà noté comme risque dans `HANDOFF.md` depuis le début du projet. Une
  revue CEO (2026-07-13, cadrage du dashboard Paramètres) a identifié ce
  point comme ayant potentiellement un meilleur ROI qu'une partie des
  réglages déjà exposés, mais l'utilisateur a choisi de garder le scope du
  dashboard Paramètres tel quel pour cette itération — ce panneau reste
  donc à faire séparément. Piste : taille actuelle du cache + bouton purge
  dans l'onglet Paramètres.

- **Répertoires `downloads/`/`audio/` configurables — v2, mode sans-Docker
  uniquement.** Exclus explicitement du dashboard Paramètres v1 (décision
  CEO review 2026-07-13) : en déploiement Docker (mode recommandé), ces
  chemins sont fixés par `docker-compose.yml` et un champ formulaire ne
  peut pas relocaliser un dossier hôte arbitraire à l'intérieur du
  conteneur — les exposer comme un champ modifiable serait trompeur. Une
  v2 pourrait les rendre modifiables seulement quand l'app tourne hors
  Docker (`python app.py` direct), avec détection de mode de déploiement.

- **Presets CRF/preset x264 non exposés en granularité fine.** Le réglage
  Qualité d'encodage (2026-07-13) expose 3 paliers nommés (léger/équilibré/
  max), pas les valeurs CRF/preset brutes — décision Design volontaire pour
  rester utilisable par un public non-technique. Si un usage avancé se
  confirme, une section "Expert" repliable pourrait exposer CRF/preset
  bruts en plus des 3 paliers, sans les remplacer.

## Dette technique / nettoyage

- **`scrap_movie.py.old` et `yt_scraper.py`** à la racine : legacy, non
  utilisés par l'app web (`scrap_movie.py` sans `.old` est la version CLI
  maintenue). Mentionnés comme candidats à suppression depuis le
  05/07/2026, jamais confirmés. À supprimer si vous confirmez qu'ils sont
  bien obsolètes.

- **Zéro test automatisé sur tout le projet** (`requirements.txt` =
  Flask/flask-cors/yt-dlp seulement, pas de pytest). Constat fait pendant
  la revue Eng du dashboard Paramètres (2026-07-13) : décision volontaire
  de ne pas introduire pytest pour une seule fonctionnalité et de rester
  cohérent avec la convention existante (QA manuelle documentée). Si le
  projet grossit encore, ça vaudra le coup de réévaluer — au minimum pour
  `valider_settings()` dans `app.py`, qui est une fonction pure bon marché
  à tester (bornes numériques utilisées ensuite dans des commandes ffmpeg).

## Pistes plus anciennes (jamais implémentées)

- **Upload de fichiers externes** (hors `downloads/`) pour le Medley, pour
  importer des vidéos qui ne sont pas déjà dans la bibliothèque.
- **Transitions vidéo entre deux vidéos indépendantes** (mentionné dans une
  spec initiale coupée) — même mécanisme xfade que les Effets/Medley.
