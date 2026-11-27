import time
from typing import Iterator, Optional

import requests


class SpotifyAPIError(RuntimeError):
    pass


class SpotifyConnector:
    AUTH_URL = "https://accounts.spotify.com/api/token"
    ARTISTS_URL = "https://api.spotify.com/v1/artists"
    ALBUMS_URL = "https://api.spotify.com/v1/albums"

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

    def get_artist_albums(
        self,
        artist_id: str,
        page_size: int = 10,
    ) -> Iterator[dict]:
        if not artist_id:
            raise ValueError("artist_id is required")
        if not 1 <= page_size <= 10:
            raise ValueError("page_size must be between 1 and 10")
        if not self.access_token:
            self.authenticate()

        offset = 0
        seen_album_ids = set()
        while True:
            response = self._api_request(
                "GET",
                f"{self.ARTISTS_URL}/{artist_id}/albums",
                params={
                    "include_groups": "album,single,compilation,appears_on",
                    "limit": page_size,
                    "offset": offset,
                },
            )
            result = response.json()
            albums = result.get("items", [])
            if not albums:
                break

            for album in albums:
                album_id = album.get("id")
                if album_id and album_id not in seen_album_ids:
                    seen_album_ids.add(album_id)
                    yield album

            offset += len(albums)
            total = result.get("total")
            if not result.get("next") or (total is not None and offset >= total):
                break

    def get_album_tracks(
        self,
        album_id: str,
        page_size: int = 10,
    ) -> Iterator[dict]:
        if not album_id:
            raise ValueError("album_id is required")
        if not 1 <= page_size <= 10:
            raise ValueError("page_size must be between 1 and 10")
        if not self.access_token:
            self.authenticate()

        offset = 0
        while True:
            response = self._api_request(
                "GET",
                f"{self.ALBUMS_URL}/{album_id}/tracks",
                params={"limit": page_size, "offset": offset},
            )
            result = response.json()
            tracks = result.get("items", [])
            if not tracks:
                break

            yield from tracks
            offset += len(tracks)
            total = result.get("total")
            if not result.get("next") or (total is not None and offset >= total):
                break

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

    def _api_request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        for attempt in range(self.max_retries):
            headers["Authorization"] = f"Bearer {self.access_token}"
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=self.timeout,
                    headers=headers,
                    **kwargs,
                )
                if response.status_code == 401:
                    if attempt == self.max_retries - 1:
                        break
                    self.authenticate()
                    continue
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                    if attempt == self.max_retries - 1:
                        break
                    time.sleep(retry_after)
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
