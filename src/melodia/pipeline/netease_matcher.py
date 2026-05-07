"""Netease Cloud Music matcher — matches QQ songs to Netease IDs and enriches metadata."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from ..models.song import Song
from ..models.store import Store
from ..config import MelodiaConfig
from .netease_client import NeteaseClient

logger = logging.getLogger(__name__)


class NeteaseMatcher:
    """Match QQ Music songs to Netease Cloud Music and enrich metadata."""

    def __init__(self, config: MelodiaConfig, store: Store):
        self.config = config
        self.store = store
        self.client = NeteaseClient(config.netease)

    async def match_all(self, songs: list[Song], batch_size: int = 5) -> list[Song]:
        """Match a list of songs to Netease and enrich with metadata.

        Args:
            songs: Songs from QQ Music import (no netease_id yet)
            batch_size: Concurrent request limit
        """
        matched = []
        semaphore = asyncio.Semaphore(batch_size)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
        ) as progress:
            task = progress.add_task("Matching songs to Netease...", total=len(songs))

            async def match_one(song: Song) -> Song:
                async with semaphore:
                    try:
                        return await self._match_and_enrich(song)
                    except Exception as e:
                        logger.warning(f"Failed to match '{song.title}' by {song.artist}: {e}")
                        return song
                    finally:
                        progress.advance(task)

            tasks = [match_one(s) for s in songs]
            matched = await asyncio.gather(*tasks)

        await self.client.close()
        return matched

    async def _match_and_enrich(self, song: Song) -> Song:
        """Match a single song and enrich with Netease metadata."""
        # Step 1: Search and match
        result = await self.client.match_song(song.title, song.artist)
        if not result:
            logger.debug(f"No Netease match for '{song.title}' by {song.artist}")
            return song

        netease_id = result.get("id", 0)
        if not netease_id:
            return song

        song.netease_id = netease_id
        song.netease_song_id = result.get("id", netease_id)

        # Fill basic info from search result
        if not song.album:
            song.album = result.get("al", {}).get("name", "")
        if not song.duration_ms:
            song.duration_ms = result.get("dt", 0)

        # Step 2: Get detailed info
        try:
            detail = await self.client.song_detail(netease_id)
            songs_data = detail.get("songs", [])
            if songs_data:
                s = songs_data[0]
                song.duration_ms = s.get("dt", song.duration_ms)
                album = s.get("al", {})
                if album.get("name"):
                    song.album = album["name"]
        except Exception as e:
            logger.debug(f"Failed to get detail for {netease_id}: {e}")

        # Step 3: Get lyrics
        try:
            lyric_data = await self.client.lyric(netease_id)
            lrc = lyric_data.get("lrc", {}).get("lyric", "")
            if lrc:
                # Strip timestamps: [00:12.34]text → text
                import re
                song.lyrics = re.sub(r"\[\d+:\d+\.\d+\]", "", lrc).strip()
        except Exception as e:
            logger.debug(f"Failed to get lyrics for {netease_id}: {e}")

        # Step 4: Get similar songs
        try:
            simi = await self.client.simi_song(netease_id, limit=10)
            song.similar_song_ids = [
                s["id"] for s in simi.get("songs", []) if "id" in s
            ]
        except Exception as e:
            logger.debug(f"Failed to get similar songs for {netease_id}: {e}")

        # Step 5: Get similar artists
        try:
            artists = result.get("ar", [])
            if artists:
                artist_id = artists[0].get("id", 0)
                if artist_id:
                    simi_artists = await self.client.simi_artist(artist_id, limit=5)
                    song.similar_artist_names = [
                        a.get("name", "") for a in simi_artists.get("artists", [])
                    ]
        except Exception as e:
            logger.debug(f"Failed to get similar artists: {e}")

        # Save to store
        self.store.upsert_song(song)
        return song

    async def enrich_by_netease_id(self, netease_id: int) -> Optional[Song]:
        """Enrich an existing song by its Netease ID (e.g. from Netease playlist)."""
        existing = self.store.get_song(netease_id)
        if existing and existing.lyrics:
            return existing  # Already enriched

        song = existing or Song(title="", artist="", netease_id=netease_id)
        return await self._match_and_enrich_by_id(song, netease_id)

    async def _match_and_enrich_by_id(self, song: Song, netease_id: int) -> Song:
        """Enrich a song when we already have the Netease ID."""
        song.netease_id = netease_id
        song.netease_song_id = netease_id

        # Get detail
        try:
            detail = await self.client.song_detail(netease_id)
            songs_data = detail.get("songs", [])
            if songs_data:
                s = songs_data[0]
                song.title = s.get("name", song.title)
                song.artist = " / ".join(a.get("name", "") for a in s.get("ar", []))
                song.album = s.get("al", {}).get("name", "")
                song.duration_ms = s.get("dt", 0)
        except Exception as e:
            logger.warning(f"Failed to get detail for {netease_id}: {e}")
            return song

        # Lyrics + similar (same as _match_and_enrich)
        try:
            lyric_data = await self.client.lyric(netease_id)
            lrc = lyric_data.get("lrc", {}).get("lyric", "")
            if lrc:
                import re
                song.lyrics = re.sub(r"\[\d+:\d+\.\d+\]", "", lrc).strip()
        except Exception:
            pass

        try:
            simi = await self.client.simi_song(netease_id, limit=10)
            song.similar_song_ids = [s["id"] for s in simi.get("songs", []) if "id" in s]
        except Exception:
            pass

        self.store.upsert_song(song)
        return song
