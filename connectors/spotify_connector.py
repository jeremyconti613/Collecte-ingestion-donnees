import time
from typing import Iterator, Optional

import requests


class SpotifyAPIError(RuntimeError):
    pass


class SpotifyConnector:
    AUTH_URL = "https://accounts.spotify.com/api/token"
    SEARCH_URL = "https://api.spotify.com/v1/search"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        timeout: int = 30,
        max_retries: int = 4,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError(
                "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required"
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.max_retries = max_retries
        self.access_token: Optional[str] = None

    def authenticate(self) -> None:
        response = self._request(
            "POST",
            self.AUTH_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = response.json()
        self.access_token = payload.get("access_token")
        if not self.access_token:
            raise SpotifyAPIError("Spotify authentication did not return an access token")

    def search_tracks(
        self,
        query: str,
        market: Optional[str] = None,
        limit: int = 50,
        max_tracks: Optional[int] = None,
    ) -> Iterator[dict]:
        if not self.access_token:
            self.authenticate()

        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")

        offset = 0
        emitted = 0
        while max_tracks is None or emitted < max_tracks:
            page_limit = limit
            if max_tracks is not None:
                page_limit = min(limit, max_tracks - emitted)

            params = {
                "q": query,
                "type": "track",
                "limit": page_limit,
                "offset": offset,
            }
            if market:
                params["market"] = market

            response = self._request(
                "GET",
                self.SEARCH_URL,
                params=params,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            page = response.json()
            tracks = page.get("tracks", {}).get("items", [])
            if not tracks:
                break

            for track in tracks:
                yield self._transform_track(track)
                emitted += 1
                if max_tracks is not None and emitted >= max_tracks:
                    break

            offset += len(tracks)
            total = page.get("tracks", {}).get("total")
            if total is not None and offset >= total:
                break

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=self.timeout,
                    **kwargs,
                )
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                    if attempt == self.max_retries - 1:
                        break
                    time.sleep(retry_after)
                    continue

                if response.status_code == 401 and url == self.SEARCH_URL:
                    self.authenticate()
                    if "headers" in kwargs:
                        kwargs["headers"]["Authorization"] = (
                            f"Bearer {self.access_token}"
                        )
                    continue

                if 500 <= response.status_code < 600:
                    if attempt == self.max_retries - 1:
                        break
                    time.sleep(2**attempt)
                    continue

                if not response.ok:
                    detail = response.text[:500]
                    raise SpotifyAPIError(
                        f"Spotify API returned HTTP {response.status_code}: {detail}"
                    )
                return response
            except requests.RequestException as exc:
                if attempt == self.max_retries - 1:
                    raise SpotifyAPIError(
                        f"Spotify API request failed after {self.max_retries} attempts"
                    ) from exc
                time.sleep(2**attempt)

        raise SpotifyAPIError(
            f"Spotify API request was not successful after {self.max_retries} attempts"
        )

    @staticmethod
    def _transform_track(track: dict) -> dict:
        album = track.get("album") or {}
        artists = track.get("artists") or []
        external_ids = track.get("external_ids") or {}

        return {
            "event_type": "spotify.track",
            "spotify_track_id": track.get("id"),
            "name": track.get("name"),
            "popularity": track.get("popularity"),
            "duration_ms": track.get("duration_ms"),
            "explicit": track.get("explicit"),
            "release_date": album.get("release_date"),
            "album": {
                "id": album.get("id"),
                "name": album.get("name"),
            },
            "artists": [
                {"id": artist.get("id"), "name": artist.get("name")}
                for artist in artists
            ],
            "external_ids": external_ids,
            "spotify_url": (track.get("external_urls") or {}).get("spotify"),
        }
