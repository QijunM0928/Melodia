"""Data models for Melodia."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Song:
    """A song with metadata from multiple sources."""

    # Core identity
    title: str
    artist: str
    album: str = ""

    # Source IDs
    qq_id: str = ""
    netease_id: int = 0
    netease_song_id: int = 0  # song URL ID (may differ from detail ID)

    # Metadata
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    mood: str = ""
    duration_ms: int = 0

    # Audio features (librosa-extracted)
    tempo: float = 0.0
    energy: float = 0.0
    valence: float = 0.0  # proxy: spectral centroid inverse
    danceability: float = 0.0
    acousticness: float = 0.0
    brightness: float = 0.0  # spectral centroid
    key: int = -1
    mode: int = -1  # 0=minor, 1=major

    # Enrichment
    lyrics: str = ""
    wiki_summary: str = ""
    similar_song_ids: list[int] = field(default_factory=list)
    similar_artist_names: list[str] = field(default_factory=list)

    # User interaction
    play_count: int = 0
    skip_count: int = 0
    is_favorite: bool = False

    # Embedding cache
    embedding_id: str = ""  # ChromaDB doc ID

    @property
    def search_text(self) -> str:
        """Rich text for embedding: combines all metadata."""
        parts = [f"{self.title} by {self.artist}"]
        if self.album:
            parts.append(f"Album: {self.album}")
        if self.genres:
            parts.append(f"Genre: {', '.join(self.genres)}")
        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")
        if self.mood:
            parts.append(f"Mood: {self.mood}")
        if self.tempo > 0:
            parts.append(f"Tempo: {self.tempo:.0f} BPM")
        if self.wiki_summary:
            parts.append(self.wiki_summary[:200])
        return ". ".join(parts)

    @property
    def has_audio_features(self) -> bool:
        return self.tempo > 0


@dataclass
class TasteProfile:
    """User's music taste profile — the soul of Melodia."""

    # Layer 1: Dimension anchors
    top_genres: list[str] = field(default_factory=list)
    top_artists: list[str] = field(default_factory=list)
    audio_feature_distribution: dict = field(default_factory=dict)

    # Layer 2: Explanatory narrative (the "why")
    narrative: str = ""
    dimension_insights: list[str] = field(default_factory=list)
    # e.g. ["你被空间感强的制作吸引", "bridge 的情感转折是强预测因子"]

    # Layer 3: Preference vectors
    positive_centroid: list[float] = field(default_factory=list)
    negative_centroid: list[float] = field(default_factory=list)
    sub_centroids: dict[str, list[float]] = field(default_factory=dict)  # genre→centroid

    # Anti-patterns (learned from feedback)
    anti_patterns: list[str] = field(default_factory=list)
    # e.g. ["不喜欢过度修音的人声", "避免纯电子无旋律"]

    # Metadata
    song_count: int = 0
    interaction_count: int = 0
    last_updated: str = ""

    def narrative_prefix(self, max_chars: int = 300) -> str:
        """Short narrative for prompt injection."""
        if not self.narrative:
            return ""
        return self.narrative[:max_chars]


@dataclass
class Recommendation:
    """A single song recommendation with explanation."""

    song: Song
    reason: str = ""
    confidence: float = 0.0
    matched_dimensions: list[str] = field(default_factory=list)
    is_exploratory: bool = False  # "calculated risk" pick


@dataclass
class Feedback:
    """User feedback on a recommendation."""

    song_id: int  # netease_id
    feedback_type: str  # "play_complete", "skip", "favorite", "replay", "dialogue"
    value: float = 0.0  # +1/-1 scale
    context: str = ""  # dialogue text if explicit


@dataclass
class DeepDiveResult:
    """Multi-dimensional decomposition of a song."""

    song: Song
    dimensions: dict[str, str] = field(default_factory=dict)
    # e.g. {"Production": "reverb-heavy, layered synths", "Emotion": "melancholic build-up"}
    recommendations_by_dim: dict[str, list[Recommendation]] = field(default_factory=dict)
