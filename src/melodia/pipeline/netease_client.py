"""Netease Cloud Music API client.

Wraps the self-hosted NeteaseCloudMusicApiEnhanced HTTP API.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import httpx

from ..config import NeteaseConfig


class NeteaseClient:
    """Async client for NeteaseCloudMusicApiEnhanced."""

    def __init__(self, config: NeteaseConfig):
        self.base_url = config.base_url.rstrip("/")
        self.cookie = config.cookie
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time = 0.0
        self._min_interval = 0.2  # 5 req/s rate limit
        self._request_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.cookie:
                headers["Cookie"] = self.cookie
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
                trust_env=False,
            )
        return self._client

    async def _rate_limited_request(self, method: str, path: str, **kwargs) -> dict:
        """Make a rate-limited API request."""
        async with self._request_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.monotonic()

            client = await self._get_client()
            resp = await client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    aclose = close  # alias for consistency

    # --- Search ---

    async def search(self, keywords: str, limit: int = 10, type: int = 1) -> dict:
        """Search songs. type=1 for tracks, 100 for artists, 1000 for playlists."""
        result = await self._rate_limited_request(
            "GET", "/search", params={"keywords": keywords, "limit": limit, "type": type}
        )
        self._normalize_search_result(result)
        return result

    async def search_default(self) -> dict:
        return await self._rate_limited_request("GET", "/search/default")

    # --- Song ---

    async def song_detail(self, ids: str | int | list[int]) -> dict:
        """Get song details. ids can be comma-separated string or list."""
        if isinstance(ids, list):
            ids = ",".join(str(i) for i in ids)
        return await self._rate_limited_request(
            "GET", "/song/detail", params={"ids": str(ids)}
        )

    async def song_url(self, id: int, level: str = "exhigh") -> dict:
        """Get song playback URL. level: standard/exhigh/lossless/hires."""
        return await self._rate_limited_request(
            "GET", "/song/url/v1", params={"id": id, "level": level}
        )

    async def lyric(self, id: int) -> dict:
        """Get song lyrics."""
        return await self._rate_limited_request("GET", "/lyric", params={"id": id})

    async def simi_song(self, id: int, limit: int = 10) -> dict:
        """Get similar songs."""
        return await self._rate_limited_request(
            "GET", "/simi/song", params={"id": id, "limit": limit}
        )

    async def simi_artist(self, id: int, limit: int = 10) -> dict:
        """Get similar artists."""
        return await self._rate_limited_request(
            "GET", "/simi/artist", params={"id": id, "limit": limit}
        )

    # --- Artist ---

    async def artist_detail(self, id: int) -> dict:
        return await self._rate_limited_request("GET", "/artist/detail", params={"id": id})

    async def artist_songs(self, id: int, limit: int = 50, order: str = "hot") -> dict:
        return await self._rate_limited_request(
            "GET", "/artist/songs", params={"id": id, "limit": limit, "order": order}
        )

    # --- Playlist ---

    async def playlist_detail(self, id: int) -> dict:
        return await self._rate_limited_request("GET", "/playlist/detail", params={"id": id})

    async def playlist_track_all(self, id: int, limit: int = 100) -> dict:
        return await self._rate_limited_request(
            "GET", "/playlist/track/all", params={"id": id, "limit": limit}
        )

    # --- Personal (requires auth) ---

    async def recommend_songs(self) -> dict:
        """Get personalized recommendations (requires cookie auth)."""
        return await self._rate_limited_request("GET", "/recommend/songs")

    async def personal_fm(self) -> dict:
        """Get personal FM tracks (requires cookie auth)."""
        return await self._rate_limited_request("GET", "/personal_fm")

    # --- Utility ---

    async def match_song(self, title: str, artist: str) -> Optional[dict]:
        """Search and find the best matching song for title+artist.

        Returns the first result's detail dict, or None if no match found.
        """
        query = f"{title} {artist}"
        result = await self.search(query, limit=5)
        songs = result.get("result", {}).get("songs", [])
        if not songs:
            return None

        # Pick the best match: prefer exact title+artist match
        for song in songs:
            song_title = song.get("name", "").lower().strip()
            song_artists = " ".join(a.get("name", "") for a in song.get("ar", [])).lower().strip()
            if song_title == title.lower().strip() and artist.lower().strip() in song_artists:
                return song

        # Fallback: first result
        return songs[0]

    def _normalize_search_result(self, result: dict):
        """Normalize /search response shape to the /cloudsearch fields used downstream."""
        songs = result.get("result", {}).get("songs", [])
        for song in songs:
            if "ar" not in song and "artists" in song:
                song["ar"] = song.get("artists") or []
            if "al" not in song and "album" in song:
                song["al"] = song.get("album") or {}
            if "dt" not in song and "duration" in song:
                song["dt"] = song.get("duration") or 0
