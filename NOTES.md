# Notes

## Déploiement VPS

Procédure de mise à jour : `MANUEL-DEPLOIEMENT-OPENROUTER.md`, §10.

- **Accès depuis le poste de dev** : `video.diamatlas.com` ne se résout pas depuis
  cette machine (constaté le 2026-11-10), et aucune IP ni entrée `~/.ssh/config`
  n'est enregistrée pour le VPS. Il faut l'IP (ou un alias SSH) et une clé
  autorisée pour l'utilisateur `django` avant de pouvoir déployer.
- **Interruption** : `build --no-cache` puis `up -d` reconstruit l'image et
  redémarre le conteneur, donc le service est brièvement coupé.
- **`--no-cache`** : voulu, pour récupérer la dernière version de yt-dlp, qui
  vieillit vite.
- **Service worker** : `static/sw.js` met l'app en cache sous `VERSION`. Après un
  changement de `static/` (icônes, manifest, index.html), incrémenter `VERSION`
  pour que les clients rechargent (passé en `v2` avec le nouveau logo).
