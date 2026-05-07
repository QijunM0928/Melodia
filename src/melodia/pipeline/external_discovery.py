"""External music discovery providers."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

import httpx

from ..models.song import Song
from ..models.store import Store

logger = logging.getLogger(__name__)


def external_song_id(source: str, title: str, artist: str) -> int:
    """Stable negative ID for externally discovered tracks."""
    key = f"{source}\0{title}\0{artist}".casefold().encode("utf-8")
    value = int(hashlib.sha1(key).hexdigest()[:12], 16)
    return -(value % 2_000_000_000 + 1)


class ITunesDiscovery:
    """Discover candidate tracks from the public iTunes Search API."""

    base_url = "https://itunes.apple.com/search"

    def __init__(self, store: Store, country: str = "US"):
        self.store = store
        self.country = country
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def available(self) -> bool:
        return True

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def _search(self, term: str, limit: int) -> list[dict]:
        params = {
            "term": term,
            "country": self.country,
            "media": "music",
            "entity": "song",
            "limit": max(1, min(limit, 50)),
        }
        try:
            client = await self._get_client()
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.HTTPError as exc:
            logger.debug("iTunes search failed for %r: %s", term, exc)
            return []

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    aclose = close

    async def discover(self, query: str, limit: int = 10) -> list[Song]:
        """Return external tracks seeded by the user's taste and current query."""
        existing = {
            (song.title.casefold(), song.artist.casefold())
            for song in self.store.get_all_songs()
        }

        terms = [query.strip()] if query.strip() else []
        terms.extend(self._seed_terms(limit=6))

        unique: list[Song] = []
        seen = set(existing)
        for term in terms:
            results = await self._search(term, limit=max(5, limit))
            for item in results:
                song = self._song_from_result(item)
                key = (song.title.casefold(), song.artist.casefold())
                if not song.title or not song.artist or key in seen:
                    continue
                seen.add(key)
                unique.append(song)
                if len(unique) >= limit:
                    return unique
        return unique

    def _seed_terms(self, limit: int = 6) -> list[str]:
        profile = self.store.load_taste_profile()
        terms = []
        if profile and profile.top_artists:
            terms.extend(profile.top_artists[:limit])
        if profile and profile.top_genres:
            terms.extend(profile.top_genres[:limit])
        if not terms:
            terms.extend(song.artist for song in self.store.get_all_songs()[:limit] if song.artist)
        return terms[:limit]

    def _song_from_result(self, item: dict) -> Song:
        title = item.get("trackName", "")
        artist = item.get("artistName", "")
        album = item.get("collectionName", "")
        genres = [item["primaryGenreName"]] if item.get("primaryGenreName") else []
        tags = ["iTunes", "外部发现"]
        if item.get("previewUrl"):
            tags.append("试听")
        return Song(
            title=title,
            artist=artist,
            album=album,
            netease_id=external_song_id("itunes", title, artist),
            genres=genres,
            tags=tags,
            duration_ms=item.get("trackTimeMillis", 0) or 0,
            wiki_summary=item.get("trackViewUrl", ""),
        )
