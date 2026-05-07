"""Taste profile generation and management."""

from __future__ import annotations

import logging
from typing import Optional

from ..models.song import Song, TasteProfile
from ..models.store import Store
from ..engine.vector_store import VectorStore

logger = logging.getLogger(__name__)

TASTE_PROFILE_PROMPT = """Analyze the following song collection and generate a multi-dimensional taste profile.

SONGS (with metadata and audio features):
{songs_data}

Generate a taste profile that explains WHY these songs appeal to the listener, not just WHAT they are.

Focus on:
1. **Production qualities**: reverb, stereo width, layering, texture
2. **Emotional patterns**: what emotional states recur? what emotional arcs?
3. **Musical preferences**: harmonic complexity, rhythm patterns, key preferences
4. **Vocal preferences**: vocal style, range, processing
5. **Atmospheric qualities**: spatial, temporal, environmental associations
6. **Anti-patterns**: what is noticeably ABSENT from this collection?

For each pattern, provide:
- A descriptive name (e.g., "spatial_production", "emotional_bridge_arc")
- A natural language explanation
- A confidence score (0-1)
- 3-5 representative song titles

Output as structured YAML with sections:
- narrative: overall taste description (2-3 paragraphs)
- dimension_insights: list of pattern objects
- anti_patterns: list of things the listener avoids
"""


def generate_taste_profile(
    songs: list[Song],
    store: Store,
    vector_store: VectorStore,
    llm_model: str = "openai/4.0Ultra",
    api_base: str = "",
    api_key: str = "",
) -> TasteProfile:
    """Generate a taste profile from the user's song collection using LLM.

    Uses top songs (by play_count + favorites) as input.
    """
    # Select representative songs
    top_songs = select_representative_songs(songs, limit=100)

    # Format for LLM
    songs_text = format_songs_for_profile(top_songs)

    # Call LLM
    import litellm
    kwargs = {"model": llm_model, "temperature": 0.7, "max_tokens": 4096}
    if api_base:
        kwargs["api_base"] = api_base
    if api_key:
        kwargs["api_key"] = api_key
    try:
        response = litellm.completion(
            **kwargs,
            messages=[
                {"role": "user", "content": TASTE_PROFILE_PROMPT.format(songs_data=songs_text)},
            ],
        )
        profile_text = response.choices[0].message.content
    except Exception as exc:
        logger.warning("LLM taste profile generation failed; using heuristic fallback: %s", exc)
        profile_text = heuristic_profile_text(top_songs, error=str(exc))

    # Parse LLM output into structured profile
    profile = parse_profile_output(profile_text, top_songs, vector_store)
    profile.song_count = len(songs)

    # Save
    store.save_taste_profile(profile)
    return profile


def heuristic_profile_text(songs: list[Song], error: str = "") -> str:
    """Build a minimal profile narrative when the configured LLM is unavailable."""
    top_artists = extract_top_artists(songs, limit=8)
    top_tags = extract_top_tags(songs, limit=8)
    parts = [
        "Taste profile generated in heuristic fallback mode because the configured LLM was unavailable.",
    ]
    if top_artists:
        parts.append(f"Recurring artists include {', '.join(top_artists)}.")
    if top_tags:
        parts.append(f"The strongest playlist clusters are {', '.join(top_tags)}.")
    if error:
        parts.append(f"LLM error: {error[:240]}")
    return "\n".join(parts)


def select_representative_songs(songs: list[Song], limit: int = 100) -> list[Song]:
    """Select the most representative songs for taste profiling.

    Prioritizes: favorites > high play_count > songs with audio features.
    """
    # Sort by relevance: favorites first, then play_count
    scored = []
    for s in songs:
        score = s.play_count + (10 if s.is_favorite else 0)
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)

    # Prefer songs with rich metadata
    selected = []
    for score, s in scored:
        if len(selected) >= limit:
            break
        if s.netease_id and (s.tags or s.genres or s.has_audio_features):
            selected.append(s)

    # Fill remaining with any songs
    for score, s in scored:
        if len(selected) >= limit:
            break
        if s not in selected and s.netease_id:
            selected.append(s)

    return selected


def format_songs_for_profile(songs: list[Song]) -> str:
    """Format song list as text for the LLM prompt."""
    lines = []
    for i, s in enumerate(songs, 1):
        parts = [f"{i}. {s.title} by {s.artist}"]
        if s.album:
            parts.append(f"Album: {s.album}")
        if s.genres:
            parts.append(f"Genre: {', '.join(s.genres)}")
        if s.tags:
            parts.append(f"Tags: {', '.join(s.tags[:5])}")
        if s.mood:
            parts.append(f"Mood: {s.mood}")
        if s.has_audio_features:
            parts.append(f"Tempo: {s.tempo:.0f} BPM")
            parts.append(f"Energy: {s.energy:.2f}")
            parts.append(f"Valence: {s.valence:.2f}")
            key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            if s.key >= 0:
                parts.append(f"Key: {key_names[s.key]} {'Major' if s.mode == 1 else 'Minor'}")
        if s.wiki_summary:
            parts.append(f"Description: {s.wiki_summary[:100]}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def parse_profile_output(
    text: str,
    songs: list[Song],
    vector_store: VectorStore,
) -> TasteProfile:
    """Parse LLM-generated profile text into a TasteProfile object.

    Falls back to heuristic extraction if LLM output is malformed.
    """
    import yaml
    import numpy as np

    # Try YAML parse
    narrative = ""
    dimension_insights = []
    anti_patterns = []

    try:
        # Extract YAML block from response
        yaml_text = text
        if "```yaml" in text:
            yaml_text = text.split("```yaml")[1].split("```")[0]
        elif "```" in text:
            yaml_text = text.split("```")[1].split("```")[0]

        data = yaml.safe_load(yaml_text)
        if isinstance(data, dict):
            narrative = data.get("narrative", "")
            dimension_insights = data.get("dimension_insights", [])
            if isinstance(dimension_insights, list):
                dimension_insights = [str(d) for d in dimension_insights]
            anti_patterns = data.get("anti_patterns", [])
    except Exception:
        # Fallback: use raw text as narrative
        narrative = text[:500] if text else "Taste profile not yet generated."

    # Compute dimensional anchors from actual data
    top_genres = extract_top_genres(songs)
    top_artists = extract_top_artists(songs)
    feature_dist = compute_feature_distribution(songs)

    # Compute preference vectors
    positive_ids = [s.netease_id for s in songs if s.is_favorite or s.play_count > 2]
    negative_ids = []  # No negative data yet at initialization

    positive_centroid = vector_store.compute_centroid(positive_ids) if positive_ids else []
    negative_centroid = []

    return TasteProfile(
        top_genres=top_genres,
        top_artists=top_artists,
        audio_feature_distribution=feature_dist,
        narrative=narrative,
        dimension_insights=dimension_insights,
        anti_patterns=anti_patterns,
        positive_centroid=positive_centroid,
        negative_centroid=negative_centroid,
        song_count=len(songs),
        interaction_count=0,
        last_updated=_now(),
    )


def extract_top_genres(songs: list[Song], limit: int = 10) -> list[str]:
    """Extract top genres from song collection."""
    from collections import Counter
    genre_counts = Counter()
    for s in songs:
        for g in s.genres:
            genre_counts[g] += 1
    if genre_counts:
        return [g for g, _ in genre_counts.most_common(limit)]
    return extract_top_tags(songs, limit=limit)


def extract_top_artists(songs: list[Song], limit: int = 10) -> list[str]:
    """Extract top artists from song collection."""
    from collections import Counter
    artist_counts = Counter()
    for s in songs:
        artist_counts[s.artist] += 1
    return [a for a, _ in artist_counts.most_common(limit)]


def extract_top_tags(songs: list[Song], limit: int = 10) -> list[str]:
    """Extract top tags from song collection."""
    from collections import Counter
    tag_counts = Counter()
    for s in songs:
        for tag in s.tags:
            tag_counts[tag] += 1
    return [tag for tag, _ in tag_counts.most_common(limit)]


def compute_feature_distribution(songs: list[Song]) -> dict:
    """Compute statistical distribution of audio features."""
    import numpy as np

    features_with_data = [s for s in songs if s.has_audio_features]
    if not features_with_data:
        return {}

    result = {}
    for feat in ["tempo", "energy", "valence", "danceability", "acousticness", "brightness"]:
        values = [getattr(s, feat) for s in features_with_data]
        if not values:
            continue
        arr = np.array(values)
        result[feat] = {
            "mean": round(float(arr.mean()), 3),
            "std": round(float(arr.std()), 3),
            "min": round(float(arr.min()), 3),
            "max": round(float(arr.max()), 3),
            "preferred_range": [round(float(arr.mean() - arr.std()), 3),
                                round(float(arr.mean() + arr.std()), 3)],
        }
    return result


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
