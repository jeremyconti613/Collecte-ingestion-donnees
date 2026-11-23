import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from connectors.spotify_connector import SpotifyAPIError, SpotifyConnector

DEFAULT_REGIONS = (
    "AD,AL,AT,BA,BE,BG,CH,CY,CZ,DE,DK,EE,ES,FI,FR,GB,GR,HR,HU,IE,IS,IT,"
    "LI,LT,LU,LV,MC,MD,ME,MK,MT,NL,NO,PL,PT,RS,SE,SI,SK,SM,TR,UA,XK,"
    "AG,AR,BB,BO,BR,BS,BZ,CA,CL,CO,CR,DM,DO,EC,GD,GT,GY,HN,HT,JM,KN,"
    "LC,MX,NI,PA,PE,PY,SR,SV,TT,US,UY,VC,VE"
)
DEFAULT_QUERIES = (
    "genre:pop,genre:hip-hop,genre:rock,genre:dance,genre:r-n-b,genre:latin"
)


def collect_market_tracks(
    connector: SpotifyConnector,
    market: str,
    queries: list[str],
    page_size: int,
    track_limit: int,
) -> list[dict]:
    tracks_by_id: dict[str, dict] = {}
    for query in queries:
        for track in connector.search_tracks(
            query=query,
            market=market,
            limit=page_size,
            max_tracks=page_size,
        ):
            track_id = track.get("spotify_track_id")
            if not track_id:
                continue
            entry = tracks_by_id.setdefault(
                track_id,
                {"track": track, "search_queries": []},
            )
            if query not in entry["search_queries"]:
                entry["search_queries"].append(query)

    ranked_tracks = sorted(
        tracks_by_id.values(),
        key=lambda entry: (
            entry["track"].get("popularity")
            if entry["track"].get("popularity") is not None
            else -1,
            entry["track"].get("spotify_track_id") or "",
        ),
        reverse=True,
    )
    return ranked_tracks[:track_limit]


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        connector = SpotifyConnector(
            client_id=os.getenv("SPOTIFY_CLIENT_ID", ""),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", ""),
        )
        regions = [
            region.strip().upper()
            for region in os.getenv("SPOTIFY_CHART_REGIONS", DEFAULT_REGIONS).split(",")
            if region.strip()
        ]
        queries = [
            query.strip()
            for query in os.getenv(
                "SPOTIFY_SEARCH_QUERIES",
                DEFAULT_QUERIES,
            ).split(",")
            if query.strip()
        ]
        page_size = int(os.getenv("SPOTIFY_SEARCH_LIMIT", "50"))
        track_limit = int(os.getenv("SPOTIFY_TRACKS_PER_MARKET", "100"))
        if not regions:
            raise ValueError("SPOTIFY_CHART_REGIONS must contain at least one country")
        if not queries:
            raise ValueError("SPOTIFY_SEARCH_QUERIES must contain at least one query")
        if page_size < 1 or page_size > 50:
            raise ValueError("SPOTIFY_SEARCH_LIMIT must be between 1 and 50")
        if track_limit < 1 or track_limit > 100:
            raise ValueError("SPOTIFY_TRACKS_PER_MARKET must be between 1 and 100")

        output_dir = PROJECT_ROOT / "data" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "spotify_top100_approx_by_country.jsonl"
        collected_at = datetime.now(timezone.utc).isoformat()
        count = 0

        with output_file.open("w", encoding="utf-8") as stream:
            for region in regions:
                ranked_tracks = collect_market_tracks(
                    connector=connector,
                    market=region,
                    queries=queries,
                    page_size=page_size,
                    track_limit=track_limit,
                )
                for rank, entry in enumerate(ranked_tracks, start=1):
                    message = {
                        **entry["track"],
                        "event_type": "spotify.track.popularity_estimate",
                        "market": region,
                        "estimated_rank": rank,
                        "ranking_method": "search_results_by_global_popularity",
                        "search_queries": entry["search_queries"],
                        "collected_at_utc": collected_at,
                    }
                    stream.write(json.dumps(message, ensure_ascii=False) + "\n")
                    count += 1
                print(f"{region}: {len(ranked_tracks)} titres collectés")

        print(f"{count} estimations écrites dans {output_file}")
    except (SpotifyAPIError, ValueError) as exc:
        print(f"Erreur d'ingestion Spotify: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()