# Manuel utilisateur — VideoCoder Studio

Guide d'utilisation de chaque fonctionnalité de l'application, accessible à
l'adresse **http://localhost:5000** une fois lancée (`docker compose up -d`
ou `python app.py`).

Toutes les vidéos produites ou importées vivent dans `downloads/`, tous les
audios dans `audio/` — rien n'est jamais écrasé (un fichier existant est
suffixé `_1`, `_2`, …).

---

## Sommaire

1. [YouTube — téléchargement](#1-youtube--téléchargement)
2. [Réseaux sociaux — conversion WhatsApp/Instagram](#2-réseaux-sociaux--conversion-whatsappinstagram)
3. [Extraction audio](#3-extraction-audio)
4. [Découpage](#4-découpage)
5. [Medley multi-clips](#5-medley-multi-clips)
6. [Radio](#6-radio)
7. [Images](#7-images)
8. [Bande musicale](#8-bande-musicale)
9. [Titre](#9-titre)
10. [Effets d'intro/outro](#10-effets-dintrooutro)
11. [Bibliothèque](#11-bibliothèque)
12. [Recherche, numéro, date — dans toutes les listes](#12-recherche-numéro-date--dans-toutes-les-listes)
13. [Suivi de progression et file d'attente](#13-suivi-de-progression-et-file-dattente)
14. [Installer l'app sur smartphone (PWA)](#14-installer-lapp-sur-smartphone-pwa)

---

## 1. YouTube — téléchargement

1. Collez l'URL d'une vidéo YouTube.
2. Un aperçu s'affiche (titre, durée, vues, miniature) avant de lancer quoi
   que ce soit.
3. Cliquez sur **Télécharger** : la vidéo est récupérée en MP4 (meilleure
   qualité disponible) dans `downloads/`, avec barre de progression.

> Si un téléchargement échoue soudainement, yt-dlp a probablement besoin
> d'une mise à jour (YouTube change souvent son fonctionnement interne) :
> `pip install -U yt-dlp` ou `docker compose build --no-cache`.

## 2. Réseaux sociaux — conversion WhatsApp/Instagram

1. Choisissez une vidéo dans la liste (ou recherchez-la, voir §12).
2. Cliquez sur **Convertir**.
3. L'app calcule automatiquement un débit vidéo visant un fichier sous
   16 Mo (limite WhatsApp), en H.264 + AAC, compatible mobile
   (`yuv420p`, lecture immédiate `faststart`).
4. Si la vidéo dépasse 90 secondes ou si le résultat dépasse malgré tout
   16 Mo, un avertissement s'affiche — les statuts WhatsApp sont limités à
   90 s.

## 3. Extraction audio

1. Choisissez une vidéo.
2. Choisissez le format de sortie : **mp3** (défaut), aac, ogg, wav ou flac.
3. Cliquez sur **Extraire** : le fichier audio va dans `audio/`.

## 4. Découpage

Pour ne garder qu'un passage d'une vidéo (couper une pub au début, par
exemple) :

1. Choisissez une vidéo — un lecteur et une **timeline de 16 miniatures**
   apparaissent.
2. Regardez la vidéo ou cliquez directement sur la timeline pour vous
   déplacer.
3. Au bon moment, cliquez **Début ici** (marque le point A) puis, plus
   loin dans la lecture, **Fin ici** (marque le point B). La zone gardée
   s'affiche en ambre sur la timeline.
4. Vous pouvez aussi taper les instants directement dans les champs
   **Début** / **Fin** (format `mm:ss` ou minutes décimales, ex. `1:30`
   ou `1.5`).
5. Cliquez **Découper** : l'extrait exact (coupe précise, pas seulement
   sur une image-clé) est produit dans `downloads/`.

## 5. Medley multi-clips

Assembler plusieurs extraits de vidéos différentes en un seul montage,
avec des transitions entre chaque clip.

**Étape 1 — Ajouter des clips**
Choisissez des vidéos une par une dans la liste ; chaque clic ajoute un
clip à la liste de montage, dans l'ordre choisi.

**Étape 2 — Ordonner et découper**
- Faites glisser un clip (poignée ⋮⋮) pour changer son ordre dans le
  montage, ou utilisez les flèches ▲▼.
- Cliquez sur l'icône ✂ d'un clip pour ouvrir son découpeur (même lecteur
  + timeline que la fonction Découpage) et fixer précisément le début et
  la fin à garder pour ce clip.
- Retirez un clip avec la croix ✕.

Entre chaque paire de clips, une ligne apparaît pour choisir la
**transition** : fondu, glissement (gauche/droite), volet
(gauche/droite), cercle (ouvrant/fermant), radial ou dissolution — et sa
**durée** (0,5 à 3 secondes). Le bouton **Appliquer à tous** applique la
même transition et durée partout d'un coup, à personnaliser ensuite clip
par clip si besoin.

**Étape 3 — Aperçu et export**
- **Prévisualiser** génère un rendu rapide en basse résolution (5
  premières secondes de chaque extrait) pour valider l'enchaînement sans
  attendre l'export complet — il s'affiche directement dans la page.
- Réglez la **résolution** (480p/720p/1080p) et le **débit** (auto = 
  qualité constante, ou faible/moyen/élevé).
- **Exporter le medley** lance la génération finale dans `downloads/`
  (`medley_Nclips.mp4`), avec barre de progression.

> Il faut au moins 2 clips pour exporter, et 12 au maximum. Une
> transition ne peut pas durer plus que la moitié du plus court des deux
> clips qu'elle relie (ajustée automatiquement si besoin).

## 6. Radio

1. **Choisir une station** : les 18 stations marocaines intégrées, ou
   utilisez le champ de recherche pour filtrer localement **et**
   interroger l'annuaire mondial Radio Browser (à partir de 2 caractères) —
   des dizaines de milliers de stations dans le monde.
2. Cliquez sur l'étoile ⭐ d'une station pour l'ajouter à vos **favoris** :
   elle apparaît alors épinglée en tête de liste, et reste mémorisée d'une
   session à l'autre (stockée dans le navigateur).
3. Vous pouvez aussi coller l'URL d'un flux personnalisé.
4. **Écouter** lance la lecture en direct dans le navigateur, avec le
   titre en cours affiché quand la station le diffuse (métadonnées ICY).
5. **Enregistrer en MP3** : choisissez une durée (en minutes) et lancez
   l'enregistrement ; le bouton **Arrêter** permet de couper avant la fin
   tout en gardant le fichier déjà enregistré.

## 7. Images

1. Choisissez une vidéo.
2. Choisissez le format (JPEG ou PNG) et l'intervalle (une image toutes
   les N secondes).
3. Cliquez sur **Extraire** : toutes les images sont livrées dans une
   archive ZIP téléchargeable depuis la Bibliothèque.

## 8. Bande musicale

1. Choisissez une vidéo et un fichier audio.
2. Choisissez le mode :
   - **Remplacer** : le son d'origine de la vidéo est retiré, remplacé
     par l'audio choisi.
   - **Mixer** : l'audio choisi est ajouté par-dessus le son d'origine.
3. Cliquez sur **Associer** : la vidéo est produite avec la nouvelle
   piste audio.

## 9. Titre

1. Choisissez une vidéo et tapez le texte à incruster.
2. Choisissez la position (haut, centre, bas) et la couleur.
3. Cliquez sur **Incruster le titre** : le texte apparaît avec un
   contour noir pour rester lisible sur n'importe quelle image.

> Les émojis ne sont pas pris en charge par la police utilisée (DejaVu) et
> s'afficheront comme des rectangles vides.

## 10. Effets d'intro/outro

1. Choisissez une vidéo.
2. Choisissez l'effet (fondu noir/blanc, cercle, balayage, glissement,
   zoom, pixellisation, flou, dissolution, volet radial…).
3. Choisissez où l'appliquer (début, fin, ou les deux) et la durée
   (0,5 à 5 s).
4. Cliquez sur **Appliquer l'effet** : la transition est ajoutée avec un
   fondu du son assorti.

## 11. Bibliothèque

Vue d'ensemble de tout ce que l'atelier a produit : vidéos (avec une
vignette prise à 10 % de la durée), audios (avec leur pochette embarquée
si elle existe), et exports d'images (ZIP). Cliquer sur une ligne ouvre ou
télécharge le fichier.

## 12. Recherche, numéro, date — dans toutes les listes

Partout où l'on choisit un fichier dans l'application (Découpage, Medley,
Images, Bande musicale, Titre, Effets, Extraction audio) comme dans la
Bibliothèque :

- un **champ de recherche** filtre la liste par nom de fichier ;
- chaque ligne affiche son **numéro** dans la liste et sa **date de
  création** ;
- les fichiers les plus récents apparaissent en premier.

## 13. Suivi de progression et file d'attente

Toute opération longue (conversion, découpage, medley, extraction…)
affiche une barre de progression en temps réel. Si plusieurs opérations
sont lancées d'affilée, les deux premières démarrent immédiatement et les
suivantes patientent avec le statut **« En file d'attente »** — elles
démarrent automatiquement dès qu'un emplacement se libère (2 encodages
simultanés par défaut). Les téléchargements YouTube et enregistrements
radio ne sont pas concernés par cette limite.

## 14. Installer l'app sur smartphone (PWA)

VideoCoder Studio peut s'installer comme une vraie application : une icône
sur l'écran d'accueil, un lancement en plein écran (sans barre de
navigateur) et un démarrage rapide.

**Condition : l'adresse doit être en `https://`** (ou `localhost`). Avec une
adresse du type `http://192.168.1.20:5000`, le téléphone ne propose pas
l'installation — l'app reste utilisable dans le navigateur. Pour activer
https, voir `MANUEL-INSTALLATION-DOCKER.md` et `HANDOFF.md` (section « PWA
et https »).

**Android (Chrome)**
1. Ouvrir l'adresse https de l'app dans Chrome.
2. Menu **⋮** puis **Installer l'application** (ou **Ajouter à l'écran
   d'accueil**).

**iPhone / iPad (Safari uniquement)**
1. Ouvrir l'adresse https de l'app dans Safari.
2. Bouton **Partager** puis **Sur l'écran d'accueil**.

**Bon à savoir**
- L'app reste un client de votre serveur : sans connexion, l'interface
  s'ouvre mais aucun traitement n'est possible (conversion, téléchargement,
  radio…).
- Si l'app est accessible depuis Internet, protégez-la par un mot de passe
  (voir `Caddyfile`) : elle n'a pas d'authentification propre.
- Après une mise à jour de l'app, fermez et rouvrez-la pour charger la
  nouvelle version.
