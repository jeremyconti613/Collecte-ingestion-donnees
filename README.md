# Collecte incrémentale de titres Spotify

## Objectif

Collecter les titres des 200 artistes source sélectionnés, dont les albums ont une date de sortie Spotify au 1er janvier 2026 ou après. Chaque occurrence par artiste, album et titre est enregistrée avec sa date d'extraction UTC.

La Web API Spotify ne fournit pas de classement exhaustif des artistes les plus populaires. Le périmètre est donc une liste fixe de 200 IDs Spotify dans `data/input/spotify_track_seed_artists.json`, conservée à l’identique entre les relances.

## Fonctionnement

Le connecteur s'authentifie avec OAuth Client Credentials, récupère par pages de 10 les albums, singles, compilations et apparitions des artistes, puis lit leurs titres. Il filtre sur la date de sortie de l'album donnée par Spotify; une réédition peut ainsi être considérée comme une sortie récente. Les dates absentes ou invalides sont ignorées.

Le résultat est ajouté à `data/output/spotify_artist_tracks_since_2026.jsonl`, un objet JSON par ligne. La clé d'idempotence est `(seed_artist_id, album_id, track_id)`: les occurrences déjà collectées sont ignorées, mais un même titre sur plusieurs albums est conservé. En cas d'interruption, les lignes déjà écrites restent présentes et la relance continue sans les dupliquer.

## Configuration et exécution

Le fichier `.env` local doit contenir les identifiants Spotify Developer et :

```dotenv
SPOTIFY_TRACK_ARTIST_LIMIT=200
```

Ne partagez pas les identifiants et ne les commitez pas. Le fichier `.env` est ignoré par Git.

Depuis la racine du dépôt, exécuter :

```powershell
python src\producers\track_producer.py
python validation\validate.py
```

La collecte peut être longue et reste soumise aux quotas Spotify. Le validateur lit le fichier incrémental généré.

## Dashboard

Démarrer le serveur depuis la racine :

```powershell
python -m http.server 8000
```

Puis ouvrir [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/). Le dashboard affiche tous les titres dans une liste unique, avec album, date, artistes crédités et lien Spotify. La recherche permet de filtrer par titre, artiste ou album.
