"""CSV playlist importer for exported song lists."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models.song import Song


TITLE_KEYS = ("Title", "title", "歌曲名", "Song", "Name", "name")
ARTIST_KEYS = ("Artist", "artist", "歌手", "Singer", "singer")
ALBUM_KEYS = ("Album", "album", "专辑")


def import_csv_playlists(path: str | Path) -> list[Song]:
    """Import one CSV file or all CSV files in a directory.

    Expected columns are Title, Artist, Album. Common Chinese/lowercase aliases
    are accepted. The source CSV filename is preserved as a tag.
    """
    path = Path(path)
    files = sorted(path.glob("*.csv")) if path.is_dir() else [path]

    merged: dict[tuple[str, str], Song] = {}
    for file in files:
        for song in _parse_csv_file(file):
            key = (song.title.casefold().strip(), song.artist.casefold().strip())
            if not key[0] or not key[1]:
                continue
            if key in merged:
                existing = merged[key]
                if not existing.album and song.album:
                    existing.album = song.album
                for tag in song.tags:
                    if tag not in existing.tags:
                        existing.tags.append(tag)
            else:
                merged[key] = song

    return list(merged.values())


def _parse_csv_file(path: Path) -> list[Song]:
    playlist_tag = path.stem
    songs: list[Song] = []

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = _first_value(row, TITLE_KEYS)
            artist = _first_value(row, ARTIST_KEYS)
            album = _first_value(row, ALBUM_KEYS)
            if not title or not artist:
                continue
            songs.append(
                Song(
                    title=title,
                    artist=artist,
                    album=album,
                    tags=[playlist_tag],
                )
            )

    return songs


def _first_value(row: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return value.strip()
    return ""
