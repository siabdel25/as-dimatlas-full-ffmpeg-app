# Étude de faisabilité — Montage « Medley » multi-clips

**Verdict : faisable sans refonte.** Chaque brique de la spécification a déjà
son équivalent dans l'app ; la fonctionnalité est un assemblage de l'existant
plus ~150 lignes de backend et ~350 lignes de frontend. Preuve de concept
ffmpeg validée (voir § PoC).

## Preuve de concept (validée le 2026-07-04)

3 clips de résolutions et cadences **différentes** (1920×1080@30,
2560×1440@60, 640×360@30), extraits de 6 s chacun, enchaînés avec deux
transitions xfade différentes (`fade` puis `circleopen`, 1 s chacune) :

- sortie 1280×720 H.264/AAC de **16,000 s** exactement (3×6 − 2×1) ;
- encodage en **4 s** (preset veryfast) dans le conteneur ;
- transitions visuellement correctes (frames vérifiées à mi-transition).

Graphe validé (généralisable à N clips) :

```
# par clip i (découpe faite en amont par -ss/-t sur chaque entrée) :
[i:v]scale=W:H:force_original_aspect_ratio=decrease,
     pad=W:H:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1,settb=AVTB,format=yuv420p[vi]
[i:a]aformat=sample_rates=44100:channel_layouts=stereo[ai]

# chaînage (offsets cumulés) :
[v0][v1]xfade=transition=T1:duration=d1:offset=O1[x1]
[x1][v2]xfade=transition=T2:duration=d2:offset=O2[vout]
[a0][a1]acrossfade=d=d1[y1] ; [y1][a2]acrossfade=d=d2[aout]

# Ok = O(k-1) + durée_extrait_k − dk   (O1 = durée_extrait_1 − d1)
```

Pièges déjà résolus dans le code (`/api/effects`) : xfade exige mêmes
dimensions, fps **et** timebase sur ses entrées → normalisation
`scale+pad+fps+setsar+settb=AVTB` par clip, `fps` avant `settb`.

## Correspondance spec → existant

| Étape de la spec | Brique existante réutilisée | À écrire |
|---|---|---|
| 1. Import + liste ordonnable | `FilePicker` (liste `downloads/`), vignettes `/api/poster` | tri drag & drop (HTML5 `draggable`, ~40 lignes, sans lib) ; l'« import » = fichiers déjà dans `downloads/` (l'upload local est un ajout séparé, voir Limites) |
| 2. Découpage A/B par clip | **tout existe** : lecteur + timeline 16 miniatures de `CutView` (`/api/thumbnails`, seek, « Début/Fin ici », champs mm:ss) | l'extraire en composant `ClipTrimmer` réutilisable (refactor léger de CutView, sans changement d'API) |
| 3. Transitions par intervalle | catalogue xfade déjà en place (`EFFETS_XFADE`) ; fade, slideleft/right, wipeleft/right, circleopen/close, radial sont tous des transitions xfade | sélecteur par intervalle + « transition par défaut » (pur front) |
| 4. Prévisualisation rapide | file d'encodage + `TaskProgress` + lecteur HTTP 206 | même endpoint que l'export avec `preview=true` : 5 premières secondes de chaque extrait, `scale 480p`, `preset ultrafast`, `crf 30` — la PoC encode 16 s de 720p en 4 s, la préview sera quasi instantanée |
| 5. Export final + progression | `lancer_ffmpeg` (progression sur la durée totale calculable), file `ENCODE_QUEUE`, `chemin_sans_ecrasement`, `terminer` | mapping résolution (480/720/1080p) et débit (auto = CRF 22/23, faible/moyen/élevé = -b:v) |

## API proposée (1 endpoint + réutilisation)

```
POST /api/medley
{
  "clips":       [{"file": "...", "t1": 12.0, "t2": 45.5}, …],   // ≥ 2 clips
  "transitions": [{"type": "fade", "duration": 1.0}, …],          // n−1 éléments
  "resolution":  "720p",          // 480p | 720p | 1080p
  "bitrate":     "auto",          // auto | low | medium | high
  "preview":     false
}
→ { "task_id": … }   // suivi via GET /api/tasks/<id> comme partout
```

Validation côté serveur : fichiers via `fichier_video_valide`, bornes t1/t2
contre `duree_video`, transitions ∈ catalogue, durée ∈ [0.5, 3],
`duration < min(extrait_k, extrait_k+1)` pour chaque intervalle.

## Vue frontend `MedleyView` (route `/medley`)

1. Liste des clips choisis : vignette (`/api/poster`), nom, extrait A→B,
   poignée de tri, croix de suppression, bouton « ajouter un clip ».
2. Clic sur un clip → panneau `ClipTrimmer` (le composant extrait de CutView).
3. Entre chaque clip : petit sélecteur transition + durée (0,5–3 s),
   avec « appliquer à tous ».
4. Boutons Prévisualiser (lecteur intégré) / Exporter (résolution + débit),
   les deux branchés sur `TaskProgress`.

## Points d'attention (résolus ou bornés)

- **Clip sans piste audio** : injecter `anullsrc` à la place de `[i:a]`
  (détection par `infos_flux`, déjà écrite).
- **Nombre d'entrées** : un `-ss/-t -i` par clip ; ffmpeg gère sans problème
  la dizaine d'entrées visée. Garde-fou : max 12 clips.
- **Progression** : durée totale = Σ extraits − Σ transitions, connue
  d'avance → la barre existante marche telle quelle.
- **Drag & drop de fichiers extérieurs** (upload) : hors périmètre de cette
  itération — l'app travaille sur `downloads/` (volume Docker). Un endpoint
  d'upload est trivial à ajouter ensuite si besoin.
- **Prévisualisation** : régénérée à chaque demande (pas de cache) ; fichier
  écrit dans `downloads/.preview/` et écrasé, pour ne pas polluer la
  bibliothèque.

## Estimation

| Lot | Volume |
|---|---|
| Backend `/api/medley` (+ anullsrc, presets qualité) | ~150 lignes |
| Extraction du composant `ClipTrimmer` depuis CutView | ~1 h, neutre |
| `MedleyView` (liste triable, transitions, préview/export) | ~350 lignes |
| Total | 1 à 2 jours, aucune migration ni dépendance nouvelle |
