"""QQ Music handoff helpers."""

from __future__ import annotations

from urllib.parse import quote_plus

from ..models.song import Song


def qq_music_search_url(song: Song) -> str:
    """Build a QQ Music web search URL for a song."""
    query = " ".join(part for part in [song.title, song.artist] if part).strip()
    return f"https://y.qq.com/n/ryqq/search?w={quote_plus(query)}"
