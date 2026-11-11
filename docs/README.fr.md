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

## Secrets injectés par Vault

Depuis la version **0.2.0**, tu peux injecter directement la variable `PFX_PASSWORD`.
Un exemple complet sans fichier secret est fourni dans `compose.vault.yaml` :

```sh
docker compose -f compose.vault.yaml up -d
```

Le Vault doit fournir `PFX_PASSWORD` à l'environnement de déploiement. Pour ton propre Compose :

```yaml
environment:
  PFX_PASSWORD: "${PFX_PASSWORD:?Injecter PFX_PASSWORD depuis le Vault}"
```

Supprimer les anciennes déclarations du secret fichier si tu n'en utilises plus. Utiliser
`compose.vault.yaml` seul, sans le fusionner avec le Compose par défaut.
La variable est prioritaire sur `PFX_PASSWORD_FILE` et `--password-file`, même si elle est vide :
une valeur invalide provoque une erreur, sans repli silencieux sur le fichier.
Sans variable, le fonctionnement par fichier reste identique. `--no-pfx` ignore les deux sources.

Le mot de passe doit contenir 12 à 4096 octets UTF-8, sans NUL. Les espaces et retours à la ligne
de la variable sont conservés exactement. Il n'est jamais affiché par l'application ; les
administrateurs ayant accès à `docker inspect` peuvent néanmoins consulter l'environnement.

Après rotation dans le Vault, réinjecter le secret puis **recréer** le conteneur :

```sh
docker compose -f compose.vault.yaml up -d --force-recreate
```

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
`PFX_PASSWORD_FILE` ou `PFX_PASSWORD` ; la rotation du fichier est détectée, celle d'une variable
nécessite de recréer le conteneur. `--no-pfx` permet une sortie PEM sans secret.
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
`latest` suit `main` après les tests et les scans. Le Compose Vault utilise ce canal pour recevoir
les reconstructions de sécurité au prochain téléchargement/redéploiement. Un tag de version ou
un digest de déploiement reste fixe et nécessite une mise à jour explicite.
Un commit `release: vX.Y.Z` sur `main` publie la version `X.Y.Z`, puis crée son tag Git et sa
release GitHub après validation du téléchargement public. Un tag Git poussé manuellement
`vX.Y.Z` déclenche également la publication de l'image correspondante.
La CI vérifie aussi que l'image peut être téléchargée sans connexion ; si GHCR a créé le package
en privé, le propriétaire doit passer sa visibilité à Public dans les paramètres du package.

Le code est sous licence MIT, les dépendances conservent leurs licences respectives.
La CI comprend tests, audit des dépendances Python, test du conteneur, SBOM et provenance.
Dependabot vérifie les dépendances et les digests tous les jours à 04 h (Europe/Paris), week-end
compris. Il ouvre des PR : il faut toujours les fusionner après validation. Le digest Python
est donc contrôlé mais peut être mis à jour ; sans fusion de la PR, l'interpréteur reste inchangé.

Chaque jour à 05 h 17 UTC (06 h 17 à Paris en hiver, 07 h 17 en été), la CI reconstruit sans cache
avec les correctifs Debian disponibles. Elle republie `latest` uniquement après succès des tests
et scans. Les versions numérotées ne sont pas modifiées par cette tâche. GitHub peut retarder une
exécution ou désactiver les tâches planifiées sur un dépôt public inactif.

Trivy bloque les vulnérabilités HIGH/CRITICAL disposant d'un correctif. Le rapport complet garde
visibles celles sans correctif. Les images AMD64 et ARM64 sont contrôlées par digest avant
promotion vers les tags destinés aux utilisateurs. Une CI verte ne signifie pas zéro CVE.

Pour mettre à jour ton conteneur : `docker compose -f compose.vault.yaml pull`, puis
`docker compose -f compose.vault.yaml up -d`. Le dépôt ne redéploie pas tes hôtes automatiquement.
Les correctifs Debian ne remplacent pas la mise à jour du digest pour corriger Python lui-même.
Voir les [réglages GitHub à activer](repository-settings.md) pour les tags et les fonctions de sécurité.
Cela ne constitue pas un audit de sécurité indépendant. Ne jamais publier de vrai `acme.json`,
de clé, de PFX ou de mot de passe dans une issue. Voir [SECURITY.md](../SECURITY.md).
