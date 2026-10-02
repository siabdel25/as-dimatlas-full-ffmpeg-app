# Manuel de déploiement — VideoCoder Studio sur VPS Debian 13

Déployer l'application sur un VPS **Debian 13 (trixie)** avec Docker, en
https sur **https://video.diamatlas.com**, installable comme PWA sur smartphone.

> Le fournisseur du VPS n'a pas d'importance : seules les étapes 1 (création
> du serveur) et 2 (DNS) changent selon son panneau d'administration.
> Le reste se fait en SSH, à l'identique partout.

```
Smartphone ──https──► Caddy (443, certificat auto) ──► VideoCoder (Flask :5000)
                                                          └─ ffmpeg / yt-dlp
```

---

## 1. Prérequis

| Élément | Recommandé |
|---|---|
| VPS | Debian 13, **2 vCPU / 2 Go RAM** minimum (ffmpeg est gourmand) |
| Disque | 40 Go ou plus : les vidéos s'accumulent dans `downloads/` |
| Domaine | sous-domaine `video.diamatlas.com` |
| Accès | IP publique du VPS + accès SSH root (ou sudo) |

## 2. DNS

Chez le registrar du domaine, créer un enregistrement :

| Type | Nom | Valeur |
|---|---|---|
| A | `video` (→ video.diamatlas.com) | IP du VPS |
| AAAA | `video` | IPv6 du VPS (optionnel) |

Seul le sous-domaine `video` pointe vers le VPS : `diamatlas.com` et les
autres sous-domaines (site, mail…) ne sont pas touchés.

Vérifier la propagation depuis votre poste (doit renvoyer l'IP du VPS) :

```bash
dig +short video.diamatlas.com
```

## 3. Sécuriser le serveur

Connexion initiale, puis mise à jour :

```bash
ssh root@IP_DU_VPS
apt update && apt full-upgrade -y
apt install -y sudo ufw fail2ban git curl ca-certificates
```

Créer un utilisateur non-root (remplacer `django` si besoin) :

```bash
adduser django
usermod -aG sudo django
mkdir -p /home/django/.ssh
cp ~/.ssh/authorized_keys /home/django/.ssh/ 2>/dev/null
chown -R django:django /home/django/.ssh && chmod 700 /home/django/.ssh
```

**Depuis un second terminal**, vérifier que `ssh django@IP_DU_VPS` fonctionne
avant d'aller plus loin. Puis désactiver la connexion root et le mot de passe
SSH :

```bash
sudo tee /etc/ssh/sshd_config.d/99-durcissement.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
EOF
sudo systemctl restart ssh
```

> Ne fermez pas votre session actuelle tant que la nouvelle connexion
> n'est pas confirmée, sinon vous risquez de vous enfermer dehors.

Pare-feu : seuls SSH, http (80, nécessaire au certificat) et https (443)
sont ouverts. Le port 5000 de l'app reste fermé :

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo systemctl enable --now fail2ban
```

> **Attention Docker et ufw** : Docker publie ses ports en contournant ufw.
> Le fichier `docker-compose.yml` publie `5000:5000` : sur un VPS public,
> remplacez-le par `127.0.0.1:5000:5000` (étape 6) pour que l'app ne soit
> joignable que via Caddy.

## 4. Installer Docker

Dépôt officiel Docker pour Debian 13 :

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
| sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER      # puis se reconnecter en SSH
docker run --rm hello-world
docker compose version
```

> Si `apt` ne trouve pas le dépôt `trixie`, utiliser le paquet Debian à la
> place : `sudo apt install -y docker.io docker-compose`.

## 5. Récupérer le projet

```bash
cd ~
git clone https://github.com/siabdel25/as-dimatlas-full-ffmpeg-app.git
cd as-dimatlas-full-ffmpeg-app
```

## 6. Configuration

```bash
cp .env.example .env
nano .env
```

Dans `.env`, décommenter et renseigner :

```
DOMAIN=video.diamatlas.com
```

Les volumes (`downloads/`, `audio/`, `config/`, `cookies/`) sont créés dans
le dossier du projet par défaut. Pour un disque dédié, voir
`MANUEL-INSTALLATION-DOCKER.md` section 4.1 (`DOWNLOADS_DIR`, etc.).

### Fermer le port 5000 au public

Dans `docker-compose.yml`, service `videocoder`, remplacer :

```yaml
    ports:
      - "5000:5000"
```

par :

```yaml
    ports:
      - "127.0.0.1:5000:5000"
```

(Caddy joint l'app par le réseau interne Docker, il n'a pas besoin du
port publié.)

### Mot de passe (obligatoire)

L'app n'a **aucune authentification** : sans protection, n'importe qui peut
lancer des téléchargements et des encodages sur votre serveur.

```bash
docker run --rm caddy caddy hash-password --plaintext 'UN_MOT_DE_PASSE_SOLIDE'
```

Copier le hash obtenu (`$2a$14$...`), puis dans `Caddyfile` décommenter le
bloc `basicauth` et remplacer `HASH` :

```
{$DOMAIN} {
	basicauth {
		admin $2a$14$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
	}
	reverse_proxy videocoder:5000
}
```

> Ne pas commiter ce hash dans le dépôt public : gardez cette modification
> locale au serveur (`git update-index --assume-unchanged Caddyfile`).

## 7. Lancer

```bash
docker compose --profile https up -d --build
docker compose --profile https ps
docker compose --profile https logs -f caddy      # Ctrl+C pour quitter
```

Dans les logs de Caddy, chercher `certificate obtained successfully`. Puis
ouvrir **https://video.diamatlas.com** : le navigateur demande l'identifiant
(`admin`) et le mot de passe.

Problèmes fréquents :

| Symptôme | Cause probable |
|---|---|
| Erreur de certificat / `challenge failed` | DNS pas encore propagé, ou ports 80/443 bloqués (pare-feu du VPS **et** du panneau du fournisseur) |
| `502 Bad Gateway` | Le conteneur `videocoder` n'est pas démarré : `docker compose logs videocoder` |
| Limite Let's Encrypt atteinte | Trop d'essais : attendre une heure, ne pas relancer en boucle |

## 8. Installer la PWA sur le téléphone

- **Android (Chrome)** : ouvrir https://video.diamatlas.com, menu ⋮ puis
  **Installer l'application**.
- **iPhone (Safari)** : Partager puis **Sur l'écran d'accueil**.

Voir `MANUEL-UTILISATEUR.md`, section 14.

## 9. YouTube : cookies

Les adresses IP de VPS sont souvent bloquées par YouTube (« Sign in to
confirm you're not a bot »). Exporter les cookies depuis un navigateur
connecté (extension « Get cookies.txt LOCALLY »), puis les copier sur le
serveur :

```bash
scp cookies.txt django@IP_DU_VPS:~/as-dimatlas-full-ffmpeg-app/cookies/
```

Le dossier est monté en lecture seule dans le conteneur, aucun
redémarrage n'est nécessaire. Les cookies expirent : à renouveler
régulièrement.

## 10. Maintenance

```bash
cd ~/as-dimatlas-full-ffmpeg-app

# Mettre à jour l'app et yt-dlp (yt-dlp vieillit vite)
git pull
docker compose --profile https build --no-cache
docker compose --profile https up -d

# Espace disque
df -h /
du -sh downloads audio

# Sauvegarder les fichiers et les réglages
tar czf ~/sauvegarde-$(date +%F).tgz downloads audio config

# Arrêter
docker compose --profile https down
```

Penser à :
- activer les **mises à jour de sécurité automatiques** :
  `sudo apt install -y unattended-upgrades` ;
- surveiller l'espace disque, car les vidéos produites ne sont jamais
  supprimées automatiquement ;
- activer les sauvegardes (snapshots) du fournisseur si elles existent.

## Récapitulatif des commandes

```bash
ssh django@IP_DU_VPS
cd as-dimatlas-full-ffmpeg-app
docker compose --profile https up -d --build     # démarrer / mettre à jour
docker compose --profile https logs -f           # suivre les logs
docker compose --profile https down              # arrêter
```
