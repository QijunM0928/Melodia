"""QQ Music playlist importer.

Parses JSON exported by qqmusic-playlist-exporter into Song objects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from ..models.song import Song


def parse_qq_playlist(data: dict | list) -> list[Song]:
    """Parse QQ Music playlist JSON into Song objects.

    Accepts:
    - A list of track objects (most common exporter format)
    - A single playlist dict with track_list/songs/tracks key
    - A list of playlist dicts
    """
    if isinstance(data, list):
        # Check if this is a flat list of tracks (has title/song_name keys)
        if data and isinstance(data[0], dict) and (
            "title" in data[0] or "song_name" in data[0] or "name" in data[0] or "singer" in data[0]
        ):
            # Flat track list — parse directly
            seen = set()
            songs = []
            for item in data:
                song = _parse_track(item)
                key = (song.title.lower().strip(), song.artist.lower().strip())
                if key not in seen:
                    seen.add(key)
                    songs.append(song)
            return songs
        # List of playlists
        songs = []
        for item in data:
            songs.extend(_parse_single_playlist(item))
        return songs
    return _parse_single_playlist(data)


def _parse_single_playlist(data: dict) -> list[Song]:
    """Parse a single playlist object."""
    # Handle different exporter formats
    track_list = data.get("track_list") or data.get("songs") or data.get("tracks") or []
    if not track_list and "data" in data:
        track_list = (
            data["data"].get("track_list")
            or data["data"].get("songs")
            or data["data"].get("tracks")
            or []
        )

    songs = []
    seen = set()
    for item in track_list:
        song = _parse_track(item)
        # Dedup by title+artist
        key = (song.title.lower().strip(), song.artist.lower().strip())
        if key not in seen:
            seen.add(key)
            songs.append(song)
    return songs


def _parse_track(item: dict) -> Song:
    """Parse a single track from QQ Music JSON."""
    # Common field name variations across exporter versions
    title = item.get("title") or item.get("song_name") or item.get("name") or ""
    artist = item.get("artist") or item.get("singer") or ""
    if isinstance(artist, list):
        artist = " / ".join(a.get("name", str(a)) if isinstance(a, dict) else str(a) for a in artist)
    elif isinstance(artist, dict):
        artist = artist.get("name", str(artist))

    album = item.get("album") or item.get("album_name") or ""
    if isinstance(album, dict):
        album = album.get("name", str(album))

    qq_id = str(item.get("id") or item.get("song_id") or item.get("mid") or "")
    duration_ms = item.get("duration") or item.get("duration_ms") or 0
    if duration_ms and duration_ms < 1000:
        # Likely in seconds
        duration_ms = int(duration_ms * 1000)

    return Song(
        title=title.strip(),
        artist=artist.strip(),
        album=album.strip(),
        qq_id=qq_id,
        duration_ms=duration_ms,
    )


def import_qq_playlist(path: str | Path) -> list[Song]:
    """Import QQ Music playlist from a JSON file."""
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return parse_qq_playlist(data)
