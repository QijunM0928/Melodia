"""SQLite storage for Melodia."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from .song import Song, Feedback, TasteProfile

DEFAULT_DB_PATH = Path.home() / ".melodia" / "songs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    netease_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT DEFAULT '',
    qq_id TEXT DEFAULT '',
    netease_song_id INTEGER DEFAULT 0,
    genres TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    mood TEXT DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    tempo REAL DEFAULT 0,
    energy REAL DEFAULT 0,
    valence REAL DEFAULT 0,
    danceability REAL DEFAULT 0,
    acousticness REAL DEFAULT 0,
    brightness REAL DEFAULT 0,
    key INTEGER DEFAULT -1,
    mode INTEGER DEFAULT -1,
    lyrics TEXT DEFAULT '',
    wiki_summary TEXT DEFAULT '',
    similar_song_ids TEXT DEFAULT '[]',
    similar_artist_names TEXT DEFAULT '[]',
    play_count INTEGER DEFAULT 0,
    skip_count INTEGER DEFAULT 0,
    is_favorite INTEGER DEFAULT 0,
    embedding_id TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    netease_id INTEGER NOT NULL,
    feedback_type TEXT NOT NULL,
    value REAL DEFAULT 0,
    context TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS taste_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_songs_artist ON songs(artist);
CREATE INDEX IF NOT EXISTS idx_songs_title ON songs(title);
"""


class Store:
    """SQLite-backed store for songs, feedback, and taste profile."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Songs ---

    def upsert_song(self, song: Song):
        """Insert or update a song."""
        self.conn.execute(
            """INSERT INTO songs (netease_id, title, artist, album, qq_id, netease_song_id,
               genres, tags, mood, duration_ms, tempo, energy, valence, danceability,
               acousticness, brightness, key, mode, lyrics, wiki_summary,
               similar_song_ids, similar_artist_names, play_count, skip_count,
               is_favorite, embedding_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(netease_id) DO UPDATE SET
               title=excluded.title, artist=excluded.artist, album=excluded.album,
               qq_id=excluded.qq_id, netease_song_id=excluded.netease_song_id,
               genres=excluded.genres, tags=excluded.tags, mood=excluded.mood,
               duration_ms=excluded.duration_ms, tempo=excluded.tempo, energy=excluded.energy,
               valence=excluded.valence, danceability=excluded.danceability,
               acousticness=excluded.acousticness, brightness=excluded.brightness,
               key=excluded.key, mode=excluded.mode, lyrics=excluded.lyrics,
               wiki_summary=excluded.wiki_summary, similar_song_ids=excluded.similar_song_ids,
               similar_artist_names=excluded.similar_artist_names,
               play_count=excluded.play_count, skip_count=excluded.skip_count,
               is_favorite=excluded.is_favorite, embedding_id=excluded.embedding_id
            """,
            (
                song.netease_id, song.title, song.artist, song.album,
                song.qq_id, song.netease_song_id,
                json.dumps(song.genres), json.dumps(song.tags), song.mood,
                song.duration_ms, song.tempo, song.energy, song.valence,
                song.danceability, song.acousticness, song.brightness,
                song.key, song.mode, song.lyrics, song.wiki_summary,
                json.dumps(song.similar_song_ids), json.dumps(song.similar_artist_names),
                song.play_count, song.skip_count, int(song.is_favorite), song.embedding_id,
            ),
        )
        self.conn.commit()

    def get_song(self, netease_id: int) -> Optional[Song]:
        row = self.conn.execute("SELECT * FROM songs WHERE netease_id = ?", (netease_id,)).fetchone()
        return self._row_to_song(row) if row else None

    def search_songs(self, query: str, limit: int = 20) -> list[Song]:
        rows = self.conn.execute(
            "SELECT * FROM songs WHERE title LIKE ? OR artist LIKE ? LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_song(r) for r in rows]

    def get_all_songs(self) -> list[Song]:
        rows = self.conn.execute("SELECT * FROM songs").fetchall()
        return [self._row_to_song(r) for r in rows]

    def get_songs_with_features(self) -> list[Song]:
        rows = self.conn.execute("SELECT * FROM songs WHERE tempo > 0").fetchall()
        return [self._row_to_song(r) for r in rows]

    def get_favorite_songs(self) -> list[Song]:
        rows = self.conn.execute("SELECT * FROM songs WHERE is_favorite = 1").fetchall()
        return [self._row_to_song(r) for r in rows]

    def song_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]

    # --- Feedback ---

    def log_feedback(self, fb: Feedback):
        self.conn.execute(
            "INSERT INTO feedback_log (netease_id, feedback_type, value, context) VALUES (?, ?, ?, ?)",
            (fb.song_id, fb.feedback_type, fb.value, fb.context),
        )
        self.conn.commit()

    def get_recent_feedback(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM feedback_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def feedback_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM feedback_log").fetchone()[0]

    # --- Taste Profile ---

    def save_taste_profile(self, profile: TasteProfile):
        import dataclasses
        data = dataclasses.asdict(profile)
        self.conn.execute(
            "INSERT INTO taste_profile (id, data) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (json.dumps(data, ensure_ascii=False),),
        )
        self.conn.commit()

    def load_taste_profile(self) -> Optional[TasteProfile]:
        row = self.conn.execute("SELECT data FROM taste_profile WHERE id = 1").fetchone()
        if not row:
            return None
        data = json.loads(row["data"])
        return TasteProfile(**data)

    # --- Helpers ---

    def _row_to_song(self, row: sqlite3.Row) -> Song:
        return Song(
            title=row["title"],
            artist=row["artist"],
            album=row["album"] or "",
            qq_id=row["qq_id"] or "",
            netease_id=row["netease_id"],
            netease_song_id=row["netease_song_id"] or 0,
            genres=json.loads(row["genres"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
            mood=row["mood"] or "",
            duration_ms=row["duration_ms"] or 0,
            tempo=row["tempo"] or 0,
            energy=row["energy"] or 0,
            valence=row["valence"] or 0,
            danceability=row["danceability"] or 0,
            acousticness=row["acousticness"] or 0,
            brightness=row["brightness"] or 0,
            key=row["key"] if row["key"] is not None else -1,
            mode=row["mode"] if row["mode"] is not None else -1,
            lyrics=row["lyrics"] or "",
            wiki_summary=row["wiki_summary"] or "",
            similar_song_ids=json.loads(row["similar_song_ids"] or "[]"),
            similar_artist_names=json.loads(row["similar_artist_names"] or "[]"),
            play_count=row["play_count"] or 0,
            skip_count=row["skip_count"] or 0,
            is_favorite=bool(row["is_favorite"]),
            embedding_id=row["embedding_id"] or "",
        )
