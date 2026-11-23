import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from connectors.spotify_connector import SpotifyAPIError, SpotifyConnector

DEFAULT_GENRES = (
    "pop,hip-hop,r&b,rock,indie pop,indie rock,dance,electronic,techno,rap,"
    "trap,drill,jazz,blues,metal,punk,reggae,country,folk,classical,latin,"
    "k-pop,gospel,soundtrack,salsa,samba,indie,indie folk,heavy metal,"
    "dance pop,folk rock,opera,world music,latin hip hop"
)
GENRE_SEARCH_TERMS = {
    "hip-hop": ("hip-hop", "hip hop", "rap", "trap", "drill", "latin hip hop"),
    "r&b": ("r&b", "contemporary r&b", "soul", "funk"),
    "rock": ("rock", "indie rock", "metal", "punk"),
    "pop": ("pop", "indie pop"),
    "dance": ("dance", "electronic", "techno"),
}


def parse_genres(config: str) -> list[str]:
    genres = list(dict.fromkeys(genre.strip() for genre in config.split(",") if genre.strip()))
    if not genres:
        raise ValueError("SPOTIFY_ARTIST_GENRES must contain at least one genre")
    return genres


def collect_artists_for_genre(
    connector: SpotifyConnector,
    genre: str,
    limit: int,
) -> list[dict]:
    unique_artists = []
    artists_by_id = {}
    for search_genre in GENRE_SEARCH_TERMS.get(genre.casefold(), (genre,)):
        remaining = limit - len(unique_artists)
        if remaining <= 0:
            break

        candidates = connector.search_artists_by_genre(
            genre=search_genre,
            limit=remaining,
        )
        for artist in candidates:
            artist_id = artist.get("id")
            if not artist_id:
                continue
            entry = artists_by_id.get(artist_id)
            if entry is None:
                entry = {"artist": artist, "matched_genre_queries": []}
                artists_by_id[artist_id] = entry
                unique_artists.append(entry)
            if search_genre not in entry["matched_genre_queries"]:
                entry["matched_genre_queries"].append(search_genre)
            if len(unique_artists) == limit:
                break
    return unique_artists


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        genres = parse_genres(os.getenv("SPOTIFY_ARTIST_GENRES", DEFAULT_GENRES))
        artists_per_genre = int(os.getenv("SPOTIFY_ARTISTS_PER_GENRE", "50"))
        if not 1 <= artists_per_genre <= 50:
            raise ValueError("SPOTIFY_ARTISTS_PER_GENRE must be between 1 and 50")

        connector = SpotifyConnector(
            client_id=os.getenv("SPOTIFY_CLIENT_ID", ""),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", ""),
        )
        output_dir = PROJECT_ROOT / "data" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "spotify_top50_artists_by_genre.jsonl"
        collected_at = datetime.now(timezone.utc).isoformat()
        count = 0

        with output_file.open("w", encoding="utf-8") as stream:
            for genre in genres:
                unique_artists = collect_artists_for_genre(
                    connector=connector,
                    genre=genre,
                    limit=artists_per_genre,
                )
                for rank, entry in enumerate(unique_artists, start=1):
                    message = {
                        "event_type": "spotify.artist.genre_search_result",
                        "genre": genre,
                        "rank": rank,
                        "ranking_method": "spotify_search_result_order",
                        "matched_genre_queries": entry["matched_genre_queries"],
                        "collected_at_utc": collected_at,
                        "artist": entry["artist"],
                    }
                    stream.write(json.dumps(message, ensure_ascii=False) + "\n")
                    count += 1
                print(f"{genre}: {len(unique_artists)} artistes récupérés")

        print(f"{count} artistes écrits dans {output_file}")
    except (SpotifyAPIError, ValueError) as exc:
        print(f"Erreur d'ingestion Spotify: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
