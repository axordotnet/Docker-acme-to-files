# Guide français

**Un fichier `acme.json` Traefik → un dossier de destination.**

Le conteneur lit les certificats gérés par Traefik v2/v3 (Let's Encrypt ou autre autorité ACME)
et les convertit pour d'autres programmes. Il ne demande ni ne renouvelle les certificats.

## Installation

1. Cloner ce dépôt et utiliser le fichier `compose.yaml`.
2. Créer un dossier de sortie dédié et un fichier secret contenant un mot de passe aléatoire
   d'au moins 12 octets pour les PFX. Exemple : `openssl rand -base64 32`.
3. Dans `.env`, définir `ACME_SOURCE_DIR` (dossier contenant `acme.json`),
   `CERT_OUTPUT_DIR`, `EXPORT_UID` et `EXPORT_GID`.
4. Le compte choisi doit pouvoir lire la source et le secret, traverser leurs dossiers parents,
   et écrire dans le dossier de sortie. Vérifier aussi les ACL sur Synology.
5. Lancer `docker compose up -d`, puis vérifier `docker compose logs -f acme-to-files`.

Les commandes complètes figurent dans le [README principal](../README.md#quick-start-linux-docker-compose).
Ne pas rendre `acme.json` accessible à tous : Traefik utilise normalement le mode `0600`.
Utiliser le même UID si approprié, ou une copie protégée. Le conteneur fonctionne par défaut
en `10001:10001`, sans réseau, sans privilèges et avec sa racine en lecture seule.

## Fichiers produits

Pour le resolver `letsencrypt` et le domaine `example.org` :
`output/current/letsencrypt/example.org/`.

| Fichier | Contenu |
| --- | --- |
| `certificate.cert` | Certificat seul, encodage PEM |
| `private.key` | Clé privée PKCS#8 PEM non chiffrée |
| `fullchain.pem` | Certificat et chaîne fournie par Traefik |
| `chain.pem` | Intermédiaires seuls |
| `bundle.pfx` | Clé + certificat + chaîne, protégés par mot de passe |
| `combined.pem` | Clé et chaîne dans le même fichier, option `--combined-pem` |

Les SAN partagent le dossier du domaine principal. `*.example.org` devient `wildcard_example.org`.
Les fichiers ont les droits `0600`, les dossiers générés `0700` : les consommateurs doivent
utiliser le même UID ou recevoir une copie avec des droits adaptés. Les anciens logiciels
exigeant un PFX RC2/3DES ne sont pas pris en charge.

## Renouvellements et fiabilité

La source est vérifiée toutes les 30 secondes (`POLL_INTERVAL`). Monter son **dossier** en
lecture seule pour détecter aussi les remplacements de fichier. Le mot de passe vient de
`PFX_PASSWORD_FILE` ; sa rotation est détectée. `--no-pfx` permet une sortie PEM sans secret.
`--once` réalise un export puis termine avec un code de retour exploitable.

Tout le fichier est validé avant publication : correspondance clé/certificat, dates, domaines
et signatures entre les éléments de chaîne fournis. Une erreur conserve le dernier export
et rend le conteneur unhealthy. Une entrée expirée bloque tout l'export. Cette validation ne
vérifie ni la confiance d'une autorité racine, ni la révocation.

Une nouvelle génération remplace atomiquement le lien `current`. La génération active et
la précédente sont conservées. Réserver entièrement la destination à cet outil. Monter le
**dossier de sortie complet** chez les consommateurs, jamais un fichier isolé ou le lien
`current` seul. Un programme lisant plusieurs fichiers doit résoudre `current` une seule fois
pour garantir qu'ils proviennent de la même génération, puis terminer sa lecture avant deux
publications suivantes. Recharger le programme après mise à jour : l'exporteur ne le redémarre pas.

Privilégier une destination locale Linux : les comportements NFS/SMB ne sont pas validés.
Surveiller la santé Docker et l'expiration des certificats ; Docker ne redémarre pas un service
simplement parce qu'il est unhealthy. Le dernier export conservé peut finir par expirer.

## Image et maintenance

Image : `ghcr.io/axordotnet/docker-acme-to-files:latest`, Linux AMD64 et ARM64.
`latest` suit `main` après les tests. En production, figer le digest de l'image.
Les tags Git `vX.Y.Z` déclenchent la publication d'une version `X.Y.Z`.
La CI vérifie aussi que l'image peut être téléchargée sans connexion ; si GHCR a créé le package
en privé, le propriétaire doit passer sa visibilité à Public dans les paramètres du package.

Le code est sous licence MIT, les dépendances conservent leurs licences respectives.
La CI comprend tests, audit des dépendances Python, test du conteneur, SBOM et provenance.
Cela ne constitue pas un audit de sécurité indépendant. Ne jamais publier de vrai `acme.json`,
de clé, de PFX ou de mot de passe dans une issue. Voir [SECURITY.md](../SECURITY.md).
