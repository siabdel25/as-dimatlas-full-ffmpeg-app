# Manuel d'installation Docker — VideoCoder Studio

Ce guide explique comment installer Docker sur **Windows**, **Linux (Debian /
Ubuntu)** et **macOS (Apple)**, puis lancer VideoCoder Studio avec
`docker compose`.

---

## Sommaire

1. [Windows](#1-windows)
2. [Linux — Debian / Ubuntu](#2-linux--debian--ubuntu)
3. [macOS (Apple)](#3-macos-apple)
4. [Lancer VideoCoder Studio (commun aux 3 plateformes)](#4-lancer-videocoder-studio-commun-aux-3-plateformes)
5. [Mettre à jour l'application après une modification du code](#5-mettre-à-jour-lapplication-après-une-modification-du-code)
6. [Dépannage](#6-dépannage)

---

## 1. Windows

Docker sur Windows fonctionne via **Docker Desktop**, qui s'appuie sur WSL2
(Windows Subsystem for Linux).

### 1.1 Prérequis

- Windows 10 64 bits (version 2004+) ou Windows 11.
- Virtualisation activée dans le BIOS/UEFI (VT-x/AMD-V).

### 1.2 Installer WSL2

Ouvrez **PowerShell en administrateur** et lancez :

```powershell
wsl --install
```

Redémarrez l'ordinateur si demandé.

### 1.3 Installer Docker Desktop

1. Téléchargez Docker Desktop depuis le site officiel de Docker
   (docker.com → Download → Docker Desktop for Windows).
2. Lancez l'installateur, laissez l'option **"Use WSL 2 instead of Hyper-V"**
   cochée.
3. Redémarrez la session Windows si demandé.
4. Lancez Docker Desktop depuis le menu Démarrer et attendez que l'icône de
   la baleine dans la barre des tâches indique "Docker Desktop is running".

### 1.4 Vérifier l'installation

Ouvrez un terminal (PowerShell ou l'invite de commandes) :

```powershell
docker --version
docker compose version
```

Les deux commandes doivent afficher un numéro de version sans erreur.

---

## 2. Linux — Debian / Ubuntu

### 2.1 Retirer d'anciennes versions (si présentes)

```bash
sudo apt remove docker docker-engine docker.io containerd runc
```

### 2.2 Installer les paquets nécessaires

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
```

### 2.3 Ajouter le dépôt officiel Docker

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

> Sur **Ubuntu**, remplacez `linux/debian` par `linux/ubuntu` dans les deux
> commandes ci-dessus (URL du dépôt GPG et de la source APT).

### 2.4 Installer Docker Engine et le plugin Compose

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
```

### 2.5 Utiliser Docker sans `sudo` (recommandé)

```bash
sudo usermod -aG docker $USER
```

Déconnectez-vous puis reconnectez-vous (ou redémarrez la session) pour que
le nouveau groupe soit pris en compte.

### 2.6 Vérifier l'installation

```bash
docker --version
docker compose version
docker run hello-world
```

---

## 3. macOS (Apple)

Docker fonctionne sur Mac via **Docker Desktop**, qui gère une machine
virtuelle Linux légère en arrière-plan.

### 3.1 Prérequis

- macOS 12 (Monterey) ou plus récent.
- Puce Apple Silicon (M1/M2/M3/M4) ou Intel — les deux sont supportées.

### 3.2 Installer Docker Desktop

1. Téléchargez Docker Desktop pour Mac depuis le site officiel de Docker
   (docker.com → Download → Docker Desktop for Mac), en choisissant la
   version correspondant à votre puce (**Apple Silicon** ou **Intel Chip**).
2. Ouvrez le fichier `.dmg` téléchargé et glissez **Docker.app** dans le
   dossier **Applications**.
3. Lancez Docker depuis le Launchpad ou le dossier Applications.
4. Autorisez les accès demandés (mot de passe administrateur, extensions
   système) lors du premier lancement.
5. Attendez que l'icône de la baleine dans la barre de menu indique
   "Docker Desktop is running".

### 3.3 Vérifier l'installation

Ouvrez **Terminal** :

```bash
docker --version
docker compose version
docker run hello-world
```

---

## 4. Lancer VideoCoder Studio (commun aux 3 plateformes)

Depuis un terminal ouvert dans le dossier du projet (celui contenant
`docker-compose.yml`) :

```bash
docker compose up -d
```

L'application est alors accessible à l'adresse :

**http://localhost:5000**

Les fichiers produits ou importés restent sur la machine hôte, dans les
dossiers `downloads/` (vidéos) et `audio/` (pistes audio) du projet — ils
sont montés en volume et survivent à l'arrêt du conteneur.

Pour arrêter l'application :

```bash
docker compose down
```

---

## 5. Mettre à jour l'application après une modification du code

Le `docker-compose.yml` du projet **ne monte que `downloads/` et `audio/`
en volume** : `app.py` et le dossier `static/` (frontend) sont copiés dans
l'image au moment du build. Un simple redémarrage ne suffit donc pas après
une modification du code — il faut reconstruire l'image :

```bash
docker compose up -d --build
```

Un `docker compose restart` seul relancerait le conteneur avec l'**ancienne**
image, sans vos derniers changements.

---

## 6. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `docker: command not found` | Docker (Desktop ou Engine) mal installé ou terminal pas relancé | Réinstaller / rouvrir un nouveau terminal |
| `permission denied` sur `docker.sock` (Linux) | Utilisateur pas dans le groupe `docker` | `sudo usermod -aG docker $USER` puis se reconnecter |
| Port 5000 déjà utilisé | Une autre appli écoute sur ce port | Libérer le port, ou changer `"5000:5000"` en `"8080:5000"` dans `docker-compose.yml` |
| Docker Desktop ne démarre pas (Windows) | WSL2 non installé/à jour | `wsl --update` puis redémarrer |
| Les changements de code n'apparaissent pas | Image non reconstruite | `docker compose up -d --build` (voir section 5) |
