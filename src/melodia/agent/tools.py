"""Agent tools — function calling definitions for the LLM."""

from __future__ import annotations

import json
from typing import Optional

from ..models.song import Song, Recommendation, Feedback
from ..models.store import Store
from ..engine.vector_store import VectorStore
from ..engine.recommender import Recommender
from ..engine.taste_profile import generate_taste_profile
from ..pipeline.netease_client import NeteaseClient
from ..config import NeteaseConfig

# Tool schemas for LLM function calling
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_songs",
            "description": "Search songs by keywords (title, artist, or description). Returns songs from the user's library first, then from Netease if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keywords"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_by_vibe",
            "description": "Recommend songs based on a vibe/mood description. Uses the user's taste profile for high-accuracy matching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vibe": {"type": "string", "description": "Vibe description, e.g. '适合深夜发呆的氛围感'"},
                    "count": {"type": "integer", "description": "Number of recommendations", "default": 5},
                },
                "required": ["vibe"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_similar",
            "description": "Recommend songs similar to a specific song. Good for deep-diving into a style.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_id": {"type": "integer", "description": "Netease song ID to find similar songs for"},
                    "count": {"type": "integer", "description": "Number of recommendations", "default": 5},
                },
                "required": ["song_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deep_dive",
            "description": "Decompose a song into 5 dimensions (Production, Emotion, Rhythm, Vocals, Atmosphere) and recommend along each dimension. Use when user wants to explore a song deeply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_id": {"type": "integer", "description": "Netease song ID to deep-dive into"},
                },
                "required": ["song_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_song_detail",
            "description": "Get detailed info about a specific song including lyrics, tags, and audio features.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_id": {"type": "integer", "description": "Netease song ID"},
                },
                "required": ["song_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_song",
            "description": "Get the playback URL for a song. Call this when user wants to play a specific song.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_id": {"type": "integer", "description": "Netease song ID"},
                },
                "required": ["song_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_feedback",
            "description": "Record user feedback on a song. Call when user explicitly likes/dislikes a recommendation or when playback behavior indicates preference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_id": {"type": "integer", "description": "Netease song ID"},
                    "feedback_type": {
                        "type": "string",
                        "enum": ["play_complete", "skip", "favorite", "replay", "dislike", "dialogue"],
                        "description": "Type of feedback",
                    },
                    "context": {"type": "string", "description": "Optional context (e.g. dialogue text for explicit feedback)"},
                },
                "required": ["song_id", "feedback_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "correct_direction",
            "description": "Handle user correction on recommendation direction. Updates taste understanding and re-searches with adjusted parameters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "correction": {"type": "string", "description": "What the user wants differently, e.g. '太吵了' or '不要电子的'"},
                    "original_vibe": {"type": "string", "description": "The original vibe description that led to the unsatisfactory recommendations"},
                },
                "required": ["correction"],
            },
        },
    },
]


class ToolExecutor:
    """Executes tool calls from the LLM."""

    def __init__(
        self,
        store: Store,
        vector_store: VectorStore,
        netease_config: NeteaseConfig,
        llm_model: str = "openai/4.0Ultra",
        api_base: str = "",
        api_key: str = "",
    ):
        self.store = store
        self.vector_store = vector_store
        self.recommender = Recommender(store, vector_store, netease_config, llm_model, api_base, api_key)
        self.netease_client = NeteaseClient(netease_config)
        self._recent_tool_results: list[dict] = []

    async def execute(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call and return the result as a string."""
        handler = getattr(self, f"_tool_{tool_name}", None)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        try:
            result = await handler(**arguments)
            if isinstance(result, dict):
                self._recent_tool_results.append(result)
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def consume_recent_recommendations(self) -> list[dict]:
        """Return recommendation cards from recent tool calls, then clear them."""
        cards: list[dict] = []
        for result in self._recent_tool_results:
            recs = result.get("recommendations", [])
            if isinstance(recs, list):
                cards.extend(recs)
        self._recent_tool_results = []
        return cards

    def _recommendation_card(self, rec: Recommendation) -> dict:
        return {
            "song": {
                "id": rec.song.netease_id,
                "title": rec.song.title,
                "artist": rec.song.artist,
                "album": rec.song.album,
                "genres": rec.song.genres,
                "tags": rec.song.tags,
                "duration_ms": rec.song.duration_ms,
            },
            "reason": rec.reason,
            "confidence": rec.confidence,
            "is_exploratory": rec.is_exploratory,
            "matched_dimensions": rec.matched_dimensions,
        }

    async def _tool_search_songs(self, query: str, limit: int = 10) -> dict:
        # Search local store first
        local = self.store.search_songs(query, limit=limit)
        if local:
            return {
                "source": "library",
                "songs": [
                    {"id": s.netease_id, "title": s.title, "artist": s.artist,
                     "album": s.album, "genres": s.genres, "tags": s.tags}
                    for s in local
                ],
            }

        # Fallback to Netease search
        result = await self.netease_client.search(query, limit=limit)
        songs = result.get("result", {}).get("songs", [])
        return {
            "source": "netease",
            "songs": [
                {"id": s.get("id"), "title": s.get("name"),
                 "artist": " / ".join(a.get("name", "") for a in s.get("ar", [])),
                 "album": s.get("al", {}).get("name", "")}
                for s in songs
            ],
        }

    async def _tool_recommend_by_vibe(self, vibe: str, count: int = 5) -> dict:
        profile = self.store.load_taste_profile()
        recs = await self.recommender.recommend_by_vibe(vibe, profile, n_final=count)
        return {
            "recommendations": [self._recommendation_card(r) for r in recs],
        }

    async def _tool_recommend_similar(self, song_id: int, count: int = 5) -> dict:
        profile = self.store.load_taste_profile()
        recs = await self.recommender.recommend_similar(song_id, profile, n=count)
        return {
            "recommendations": [self._recommendation_card(r) for r in recs],
        }

    async def _tool_deep_dive(self, song_id: int) -> dict:
        profile = self.store.load_taste_profile()
        result = await self.recommender.deep_dive(song_id, profile)
        return {
            "song": {"id": result.song.netease_id, "title": result.song.title,
                     "artist": result.song.artist},
            "dimensions": result.dimensions,
            "recommendations": {
                dim: [
                    {"song_id": r.song.netease_id, "title": r.song.title,
                     "artist": r.song.artist, "reason": r.reason}
                    for r in recs
                ]
                for dim, recs in result.recommendations_by_dim.items()
            },
        }

    async def _tool_get_song_detail(self, song_id: int) -> dict:
        song = self.store.get_song(song_id)
        if not song:
            # Try fetching from Netease
            detail = await self.netease_client.song_detail(song_id)
            songs = detail.get("songs", [])
            if songs:
                s = songs[0]
                return {
                    "id": song_id, "title": s.get("name", ""),
                    "artist": " / ".join(a.get("name", "") for a in s.get("ar", [])),
                    "album": s.get("al", {}).get("name", ""),
                    "duration_ms": s.get("dt", 0),
                }
            return {"error": f"Song {song_id} not found"}

        return {
            "id": song.netease_id, "title": song.title, "artist": song.artist,
            "album": song.album, "genres": song.genres, "tags": song.tags,
            "mood": song.mood, "duration_ms": song.duration_ms,
            "tempo": song.tempo, "energy": song.energy, "valence": song.valence,
            "danceability": song.danceability, "acousticness": song.acousticness,
            "lyrics_excerpt": song.lyrics[:200] if song.lyrics else "",
            "similar_artists": song.similar_artist_names,
        }

    async def _tool_play_song(self, song_id: int) -> dict:
        result = await self.netease_client.song_url(song_id)
        data = result.get("data", [{}])
        if data:
            return {"url": data[0].get("url", ""), "id": song_id}
        return {"error": "No playback URL available"}

    async def _tool_save_feedback(self, song_id: int, feedback_type: str, context: str = "") -> dict:
        value_map = {
            "play_complete": 1.0,
            "skip": -0.5,
            "favorite": 2.0,
            "replay": 1.5,
            "dislike": -1.0,
            "dialogue": 0.0,
        }
        fb = Feedback(
            song_id=song_id,
            feedback_type=feedback_type,
            value=value_map.get(feedback_type, 0.0),
            context=context,
        )
        self.store.log_feedback(fb)

        # Update song counters
        song = self.store.get_song(song_id)
        if song:
            if feedback_type == "play_complete":
                song.play_count += 1
            elif feedback_type == "skip":
                song.skip_count += 1
            elif feedback_type == "favorite":
                song.is_favorite = True
            self.store.upsert_song(song)

        return {"status": "recorded", "feedback_type": feedback_type}

    async def _tool_correct_direction(self, correction: str, original_vibe: str = "") -> dict:
        # Log as dialogue feedback
        profile = self.store.load_taste_profile()
        if profile:
            profile.anti_patterns.append(correction)
            self.store.save_taste_profile(profile)

        # Re-search with corrected vibe
        adjusted_vibe = f"{original_vibe} but NOT {correction}" if original_vibe else f"NOT {correction}"
        profile = self.store.load_taste_profile()
        recs = await self.recommender.recommend_by_vibe(adjusted_vibe, profile, n_final=5)
        return {
            "adjusted_vibe": adjusted_vibe,
            "recommendations": [self._recommendation_card(r) for r in recs],
        }

    async def close(self):
        await self.recommender.aclose()
        await self.netease_client.aclose()
