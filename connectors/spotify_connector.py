import time
from typing import Optional

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

    def search_artists_by_genre(
        self,
        genre: str,
        limit: int = 50,
        page_size: int = 10,
    ) -> list[dict]:
        if not genre.strip():
            raise ValueError("genre is required")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if not 1 <= page_size <= 10:
            raise ValueError("page_size must be between 1 and 10")
        if not self.access_token:
            self.authenticate()

        artists = []
        offset = 0
        while offset < limit:
            current_page_size = min(page_size, limit - offset)
            response = self._api_request(
                "GET",
                self.SEARCH_URL,
                params={
                    "q": f"genre:{genre.strip()}",
                    "type": "artist",
                    "limit": current_page_size,
                    "offset": offset,
                },
            )
            result = response.json().get("artists", {})
            page = result.get("items", [])
            if not page:
                break

            artists.extend(page)
            offset += len(page)
            total = result.get("total")
            if not result.get("next") or (total is not None and offset >= total):
                break

        return artists[:limit]

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
