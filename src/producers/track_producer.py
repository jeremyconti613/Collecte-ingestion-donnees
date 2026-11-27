import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from connectors.spotify_connector import SpotifyAPIError, SpotifyConnector

SEED_ARTISTS_PATH = PROJECT_ROOT / "data" / "input" / "spotify_track_seed_artists.json"
TRACK_OUTPUT_PATH = PROJECT_ROOT / "data" / "output" / "spotify_artist_tracks_since_2026.jsonl"
START_DATE = date(2026, 1, 1)


def load_seed_artists(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        raise ValueError(
            f"Fichier des {limit} artistes absent: {path}. "
            "Ajoutez les IDs Spotify des artistes source à ce fichier."
        )
    try:
        artists = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalide dans {path}: {exc.msg}") from exc

    if not isinstance(artists, list) or len(artists) != limit:
        raise ValueError(f"{path} doit contenir exactement {limit} artistes")
    if any(not isinstance(artist, dict) for artist in artists):
        raise ValueError(f"Chaque élément de {path} doit être un objet JSON")

    ids = [artist.get("id") for artist in artists]
    if any(not artist_id for artist_id in ids) or len(set(ids)) != limit:
        raise ValueError(f"{path} doit contenir {limit} IDs Spotify distincts")
    return artists


def occurrence_key(record: dict) -> tuple[str, str, str]:
    return (
        record["seed_artist_id"],
        record["album_id"],
        record["track_id"],
    )


def load_existing_occurrences(path: Path) -> set[tuple[str, str, str]]:
    existing = set()
    if not path.exists():
        return existing

    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                existing.add(occurrence_key(record))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(
                    f"Enregistrement existant invalide dans {path}, "
                    f"ligne {line_number}: {exc}"
                ) from exc
    return existing


def album_release_date(album: dict) -> date | None:
    value = album.get("release_date")
    if not isinstance(value, str):
        return None

    parts = value.split("-")
    try:
        if len(parts) == 1:
            return date(int(parts[0]), 1, 1)
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        if len(parts) == 3:
            return date.fromisoformat(value)
    except ValueError:
        return None
    return None


def append_new_tracks(
    connector: SpotifyConnector,
    artists: list[dict],
    output_path: Path,
    extracted_at: str,
) -> tuple[int, int, int, int]:
    existing = load_existing_occurrences(output_path)
    new_count = 0
    old_count = 0
    skipped_without_id = 0
    skipped_albums = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as output:
        for index, artist in enumerate(artists, start=1):
            artist_new_count = 0
            for album in connector.get_artist_albums(artist["id"]):
                album_id = album.get("id")
                release_date = album_release_date(album)
                if not album_id or release_date is None or release_date < START_DATE:
                    skipped_albums += 1
                    continue

                for track in connector.get_album_tracks(album_id):
                    track_id = track.get("id")
                    if not track_id:
                        skipped_without_id += 1
                        continue
                    record = {
                        "event_type": "spotify.artist.album_track",
                        "seed_artist_id": artist["id"],
                        "seed_artist_name": artist["name"],
                        "album_id": album_id,
                        "album_name": album.get("name"),
                        "album_type": album.get("album_type"),
                        "album_group": album.get("album_group"),
                        "release_date": album.get("release_date"),
                        "release_date_precision": album.get("release_date_precision"),
                        "track_id": track_id,
                        "track": track,
                        "extracted_at_utc": extracted_at,
                    }
                    key = occurrence_key(record)
                    if key in existing:
                        old_count += 1
                        continue

                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
                    existing.add(key)
                    new_count += 1
                    artist_new_count += 1

            print(
                f"{index}/{len(artists)} {artist['name'] or artist['id']}: "
                f"{artist_new_count} nouvelle(s) occurrence(s)"
            )
    return new_count, old_count, skipped_without_id, skipped_albums


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        artist_limit = int(os.getenv("SPOTIFY_TRACK_ARTIST_LIMIT", "200"))
        if artist_limit < 1:
            raise ValueError("SPOTIFY_TRACK_ARTIST_LIMIT doit être supérieur à zéro")

        artists = load_seed_artists(SEED_ARTISTS_PATH, artist_limit)
        connector = SpotifyConnector(
            client_id=os.getenv("SPOTIFY_CLIENT_ID", ""),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", ""),
        )
        extracted_at = datetime.now(timezone.utc).isoformat()
        new_count, old_count, skipped_without_id, skipped_albums = append_new_tracks(
            connector=connector,
            artists=artists,
            output_path=TRACK_OUTPUT_PATH,
            extracted_at=extracted_at,
        )

        print(
            f"Terminé : {new_count} nouvelle(s) occurrence(s), "
            f"{old_count} déjà connue(s), {skipped_albums} album(s) antérieur(s) "
            f"ou sans date exploitable, {skipped_without_id} titre(s) sans ID stable."
        )
        print(f"Fichier incrémental : {TRACK_OUTPUT_PATH}")
    except (SpotifyAPIError, ValueError) as exc:
        print(f"Erreur d'ingestion Spotify: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
