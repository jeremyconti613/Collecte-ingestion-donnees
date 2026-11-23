# Collecte et ingestion de données Spotify

## Étape 1 - Cadrage du besoin

### Contexte métier

Le projet compare les artistes que Spotify retourne pour des recherches par genre. L'objectif est d'explorer les résultats de recherche par genre et de conserver leur ordre tel que renvoyé par Spotify.

**Question analytique :** quels artistes apparaissent dans les résultats Spotify pour chaque genre configuré ?

### Source et données

- API : Spotify Web API, endpoint `GET /v1/search` avec `type=artist` et le filtre `genre`.
- Format source : JSON.
- Accès : OAuth 2.0 Client Credentials.
- Fréquence : collecte quotidienne ou à la demande.
- Volume : jusqu'à 50 artistes candidats par genre et par exécution.
- Données conservées : objet artiste renvoyé par Spotify, notamment son ID, son nom, ses images et son URL. Certains champs peuvent être absents.

**Limite importante :** la Web API ne fournit pas un classement officiel des artistes par genre ni les écoutes par pays. Les filtres de genre peuvent retourner peu ou aucun artiste; Spotify ne fournit pas de liste publique exhaustive et stable des valeurs acceptées. Les requêtes alternatives servent à élargir les résultats, sans garantir 50 artistes distincts. Le `rank` représente leur ordre de collecte, pas un classement officiel ou d'écoutes.

### Volume, vélocité et variété

- **Volume :** faible, au plus 50 artistes par genre configuré.
- **Vélocité :** faible à modérée; collecte à la demande ou planifiée.
- **Variété :** JSON semi-structuré, avec chaînes, listes et métadonnées numériques.

### Pattern et architecture

Le pattern retenu est un **batch d'extraction API** : une ou plusieurs recherches paginées par genre, déduplication par ID en gardant l'ordre fourni par Spotify et écriture JSONL. Les marchés Europe/Amériques ne peuvent pas être classés indépendamment par cette recherche; il n'y a donc pas de rang par pays.

```text
Genres (.env)
     |
     v
Spotify Web API - recherche artiste par genre
     |
     v
Résultats de recherche -> déduplication en conservant l'ordre Spotify
     |
     v
JSONL avec rang indicatif et objet artiste source
     |
     v
Validation JSON Schema
```

## Étape 2 - Connecteur Spotify

Le connecteur dans [connectors/spotify_connector.py](./connectors/spotify_connector.py) gère OAuth, les recherches d'artistes paginées par lots de 10, les erreurs temporaires, les quotas HTTP 429 et le renouvellement du jeton après HTTP 401. Le producteur dans [src/producers/producer.py](./src/producers/producer.py) déduplique les artistes par ID en conservant l'ordre de recherche et garde l'objet artiste retourné par l'API.

### Configuration

Dans `.env`, renseigner les identifiants Spotify Developer et les genres :

```dotenv
SPOTIFY_CLIENT_ID=votre_client_id
SPOTIFY_CLIENT_SECRET=votre_client_secret
SPOTIFY_ARTIST_GENRES=pop,hip-hop,rock,dance,r-n-b,latin
SPOTIFY_ARTISTS_PER_GENRE=50
```

`SPOTIFY_ARTISTS_PER_GENRE` peut être réglé entre 1 et 50. Les genres par défaut ont été testés avec des requêtes Spotify et incluent pop, hip-hop, r&b, rock, indie pop/rock, dance, electronic, techno, rap, trap, drill, jazz, blues, metal, punk, reggae, country, folk, classical, latin, k-pop, gospel, soundtrack, salsa, samba, indie, indie folk, heavy metal, dance pop, folk rock, opera, world music et latin hip hop. Pour compléter hip-hop et r&b, le producteur essaie des termes associés (hip hop/rap/trap/drill/latin hip hop; contemporary r&b/soul/funk), puis déduplique les artistes. Les termes effectivement utilisés sont consignés dans `matched_genre_queries`. Spotify peut retourner moins de 50 artistes; aucun remplissage artificiel n'est fait. Spotify ne fournit pas de catalogue officiel stable des valeurs de genre; la requête est vérifiée par ses résultats et non par un endpoint de taxonomie.

Ne jamais versionner les identifiants. `.env` est exclu par `.gitignore`; s'il est déjà suivi par Git dans votre clone, le retirer de l'index avec `git rm --cached .env`.

### Installation, collecte et validation

```powershell
python -m pip install -r requirements.txt
python src\producers\producer.py
python validation\validate.py
```

Le résultat est enregistré dans `data/output/spotify_top50_artists_by_genre.jsonl`. Chaque ligne contient le genre demandé, la position de l'artiste dans les résultats de recherche Spotify et l'objet artiste source. Cette position n'est pas un classement des écoutes ni un Top 50 officiel par genre ou par pays.

## Tableau de bord

Après avoir collecté les données, démarrez le serveur local depuis la racine du projet :

```powershell
python -m http.server 8000
```

Ouvrez ensuite [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/). Le tableau de bord lit le JSONL local, permet de filtrer par genre et par nom, affiche les profils Spotify et montre le nombre d'artistes collectés par genre. Il ne fait aucun appel externe et conserve l'avertissement sur l'ordre des résultats de recherche.
