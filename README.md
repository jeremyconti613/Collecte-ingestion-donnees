# Collecte et ingestion de données Spotify

## Étape 1 - Cadrage du besoin

### Contexte métier

L'objectif est d'étudier les titres proposés par Spotify dans plusieurs marchés d'Europe et des Amériques. Les données peuvent servir à comparer les titres, artistes et albums présents dans les résultats selon le pays.

**Question analytique initiale :** quels titres ressortent des recherches Spotify par genres dans chaque marché, et comment leur popularité Spotify se compare-t-elle entre marchés ?

### Source Spotify

- API : Spotify Web API.
- Endpoint : `GET /v1/search` avec `type=track` et un paramètre `market`.
- Format : JSON.
- Accès : OAuth 2.0 Client Credentials.
- Fréquence : extraction planifiée à la demande ou quotidienne.
- Volume : jusqu'à 50 résultats par genre et par marché ; six recherches par marché par défaut, dédupliquées et réduites à 100 titres.
- Limites : quotas API, erreur HTTP 429, latence réseau, pagination et éventuelle non-disponibilité des données selon le marché.

**Limite importante :** l'API Spotify ne fournit pas de classement officiel Top 100 par pays. Les résultats ci-dessous sont une estimation construite à partir de recherches par genre et du score `popularity` Spotify, qui est global et non spécifique au marché. Le champ `estimated_rank` n'est donc pas le rang Spotify Charts.

### Propriétés des données

- **Volume :** faible à moyen pour une extraction ponctuelle ; plusieurs milliers de titres pour des recherches ou fenêtres larges.
- **Vélocité :** données quasi statiques à mise à jour quotidienne ou hebdomadaire pour ce premier usage.
- **Variété :** données semi-structurées contenant des identifiants, du texte, des booléens, des dates, des artistes et des métadonnées d'albums.

### Pattern d'ingestion

Le pattern retenu est **batch sur API par marché et par genre**. Les réponses sont dédupliquées par identifiant de titre, triées par popularité Spotify, puis limitées à 100 par marché. Cette collecte est relançable et écrit des messages JSONL. Une évolution vers Kafka permettra ultérieurement une ingestion plus temps réel.

### Architecture initiale

```text
Genres et marchés (.env)
        |
        v
Connecteur Spotify Web API
  - OAuth Client Credentials
  - Recherches multi-genres et multi-marchés
  - Retry / backoff
        |
        v
Déduplication et estimation par popularité globale
        |
        v
JSONL par marché -> Validation JSON Schema
```

La suite prévue pourra envoyer ces messages structurés vers Kafka avec le producer, puis les conserver dans l'espace `data/output`.

## Étape 2 - Connecteur Spotify

Le connecteur est implémenté dans [connectors/spotify_connector.py](./connectors/spotify_connector.py), et le producteur construit l'estimation par marché dans [src/producers/producer.py](./src/producers/producer.py).

Fonctionnalités :

- authentification OAuth 2.0 avec les identifiants client;
- recherches par genre pour chaque marché configuré;
- déduplication des titres, tri par score global de popularité et limite configurable;
- reprise sur les erreurs réseau et HTTP temporaires;
- respect de `Retry-After` pour les erreurs HTTP 429;
- transformation des réponses en messages `spotify.track.popularity_estimate`;
- écriture JSONL par le [producer](./src/producers/producer.py);
- validation par JSON Schema dans [validation/validate.py](./validation/validate.py).

### Configuration

Renseigner les variables suivantes dans `.env` :

```dotenv
SPOTIFY_CLIENT_ID=identifiant_client
SPOTIFY_CLIENT_SECRET=secret_client
SPOTIFY_CHART_REGIONS=FR,BE,CH,GB,US
SPOTIFY_SEARCH_QUERIES=genre:pop,genre:hip-hop,genre:rock,genre:dance,genre:r-n-b,genre:latin
SPOTIFY_SEARCH_LIMIT=50
SPOTIFY_TRACKS_PER_MARKET=100
```

Créer les identifiants dans le tableau de bord Spotify Developer. Ne jamais versionner les secrets réels. `.env` est listé dans `.gitignore`, mais il était déjà suivi par Git : avant d'y remettre des identifiants, retirer son suivi avec `git rm --cached .env` puis committer cette suppression.
`SPOTIFY_SEARCH_LIMIT` doit être compris entre 1 et 50 et `SPOTIFY_TRACKS_PER_MARKET` entre 1 et 100.

La configuration fournie couvre des marchés européens et des Amériques. Ajuster `SPOTIFY_CHART_REGIONS` pour limiter les appels ou choisir des marchés précis. Le nombre de requêtes augmente avec le nombre de marchés et de genres et peut rencontrer les limites de quota Spotify.

### Installation et exécution

```bash
python -m pip install -r requirements.txt
python src/producers/producer.py
python validation/validate.py
```

Le résultat est écrit dans `data/output/spotify_top100_approx_by_country.jsonl`. Il s'agit d'une estimation par popularité globale et non des classements quotidiens officiels Spotify Charts.
