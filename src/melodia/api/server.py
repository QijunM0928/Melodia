"""FastAPI server for Melodia web UI."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import load_config, MelodiaConfig
from ..models.store import Store
from ..models.song import Song, Feedback
from ..pipeline.qq_music import qq_music_search_url

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    song_id: int
    feedback_type: str
    context: Optional[str] = None


class PlayRequest(BaseModel):
    song_id: int


class DiscoveryRequest(BaseModel):
    query: str = ""


# Lazy-initialized singletons
_store: Optional[Store] = None
_vector_store = None
_tool_executor = None
_feedback_processor = None
_itunes_discovery = None
_config: Optional[MelodiaConfig] = None
_agent = None


def _get_config() -> MelodiaConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def _get_vector_store():
    global _vector_store
    if _vector_store is None:
        from ..engine.vector_store import VectorStore
        _vector_store = VectorStore()
    return _vector_store


def _get_tool_executor():
    global _tool_executor
    if _tool_executor is None:
        from ..engine.vector_store import VectorStore
        from ..agent.tools import ToolExecutor
        config = _get_config()
        _tool_executor = ToolExecutor(
            _get_store(), _get_vector_store(), config.netease,
            llm_model=config.llm.model, api_base=config.llm.api_base, api_key=config.llm.api_key,
        )
    return _tool_executor


def _get_feedback_processor():
    global _feedback_processor
    if _feedback_processor is None:
        from ..feedback.updater import FeedbackProcessor
        config = _get_config()
        _feedback_processor = FeedbackProcessor(
            _get_store(), _get_vector_store(),
            llm_model=config.llm.model, api_base=config.llm.api_base, api_key=config.llm.api_key,
        )
    return _feedback_processor


def _get_itunes_discovery():
    global _itunes_discovery
    if _itunes_discovery is None:
        from ..pipeline.external_discovery import ITunesDiscovery
        _itunes_discovery = ITunesDiscovery(_get_store())
    return _itunes_discovery


def _get_agent():
    global _agent
    if _agent is None:
        from ..agent.agent import Agent
        config = _get_config()
        _agent = Agent(config, _get_store(), _get_tool_executor())
    return _agent


def _song_payload(song: Song) -> dict:
    return {
        "id": song.netease_id,
        "title": song.title,
        "artist": song.artist,
        "album": song.album,
        "genres": song.genres,
        "tags": song.tags,
        "duration_ms": song.duration_ms,
    }


def _recommendation_card(song: Song, reason: str, confidence: float = 0.72) -> dict:
    return {
        "song": _song_payload(song),
        "reason": reason,
        "confidence": confidence,
        "is_exploratory": False,
        "matched_dimensions": song.tags[:2] if song.tags else [],
    }


def _is_itunes_song(song: Song) -> bool:
    return song.netease_id < 0 and "iTunes" in song.tags


def _dedupe_songs(songs: list[Song], limit: int, exclude_ids: set[int] | None = None) -> list[Song]:
    exclude_ids = exclude_ids or set()
    unique = []
    seen = set(exclude_ids)
    for song in songs:
        if song.netease_id in seen:
            continue
        seen.add(song.netease_id)
        unique.append(song)
        if len(unique) >= limit:
            break
    return unique


def _clean_profile_narrative(text: str) -> str:
    cleaned = text.strip()
    if "```yaml" in cleaned:
        cleaned = cleaned.split("```yaml", 1)[1].split("```", 1)[0].strip()
    elif cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1].strip() if len(parts) > 1 else cleaned.strip("`")
    if cleaned.startswith("narrative:"):
        cleaned = cleaned.removeprefix("narrative:").strip()
    return cleaned.strip().strip('"').strip("'")


async def _external_recommendations(message: str, limit: int = 2) -> list[dict]:
    if limit <= 0:
        return []

    try:
        songs = await _get_itunes_discovery().discover(message, limit=limit)
    except Exception as exc:
        logger.warning("External discovery failed: %s", exc)
        return []

    return [
        _recommendation_card(
            song,
            reason=(
                "iTunes 外部发现：不在当前歌单里，可先试听/查信息，"
                "完整播放交给 QQ 音乐搜索。"
            ),
            confidence=max(0.48, 0.62 - index * 0.04),
        )
        for index, song in enumerate(songs[:limit])
    ]


def _local_vector_songs(query: str, limit: int, exclude_ids: set[int] | None = None) -> list[Song]:
    store = _get_store()
    try:
        results = _get_vector_store().search(query, n_results=limit + len(exclude_ids or set()) + 8)
        songs = [store.get_song(r["id"]) for r in results]
        songs = [song for song in songs if song and not _is_itunes_song(song)]
    except Exception as exc:
        logger.warning("Discovery vector search failed, falling back to keyword search: %s", exc)
        songs = [song for song in store.search_songs(query, limit=limit + 8) if not _is_itunes_song(song)]
    return _dedupe_songs(songs, limit=limit, exclude_ids=exclude_ids)


async def _itunes_songs(query: str, limit: int, exclude_ids: set[int] | None = None) -> list[Song]:
    store = _get_store()
    saved = [
        song
        for song in store.get_all_songs()
        if _is_itunes_song(song)
        and (
            not query
            or query.casefold() in song.search_text.casefold()
            or any(query.casefold() in tag.casefold() for tag in song.tags)
        )
    ]
    songs = _dedupe_songs(saved, limit=limit, exclude_ids=exclude_ids)
    if len(songs) >= limit:
        return songs

    try:
        discovered = await _get_itunes_discovery().discover(query or "dream pop", limit=limit - len(songs))
    except Exception as exc:
        logger.warning("iTunes discovery failed: %s", exc)
        discovered = []
    return songs + _dedupe_songs(
        discovered,
        limit=limit - len(songs),
        exclude_ids={*(exclude_ids or set()), *(song.netease_id for song in songs)},
    )


async def _discovery_feed(query: str = "") -> dict:
    store = _get_store()
    profile = store.load_taste_profile()
    query = query.strip()
    seed_parts = [query]
    if profile:
        seed_parts.extend(profile.top_artists[:4])
        seed_parts.extend(profile.top_genres[:4])
        seed_parts.append(profile.narrative_prefix(180))
    seed = " ".join(part for part in seed_parts if part) or "quiet late night music"

    familiar_songs = _local_vector_songs(seed, limit=6)
    used_ids = {song.netease_id for song in familiar_songs}
    fresh_songs = await _itunes_songs(seed, limit=6, exclude_ids=used_ids)
    used_ids.update(song.netease_id for song in fresh_songs)
    edge_query = f"{seed} unexpected adjacent discovery different texture"
    edge_songs = await _itunes_songs(edge_query, limit=6, exclude_ids=used_ids)
    if not edge_songs:
        edge_songs = _local_vector_songs(edge_query, limit=6, exclude_ids=used_ids)

    dimensions = []
    if profile:
        dimensions.extend(
            {"label": artist, "kind": "artist", "weight": max(52, 92 - index * 7)}
            for index, artist in enumerate(profile.top_artists[:5])
        )
        dimensions.extend(
            {"label": genre, "kind": "cluster", "weight": max(46, 78 - index * 6)}
            for index, genre in enumerate(profile.top_genres[:5])
        )

    return {
        "query": query,
        "profile": {
            "song_count": profile.song_count if profile else store.song_count(),
            "narrative": _clean_profile_narrative(profile.narrative) if profile else "",
            "dimensions": dimensions[:8],
        },
        "sections": [
            {
                "id": "familiar",
                "title": "熟悉高命中",
                "subtitle": "从你的本地歌单语义空间里找最稳的匹配",
                "intent": "safe",
                "recommendations": [
                    _recommendation_card(
                        song,
                        reason="本地高置信：贴近当前方向，也符合你已有歌单里的稳定偏好。",
                        confidence=max(0.56, 0.84 - index * 0.04),
                    )
                    for index, song in enumerate(familiar_songs)
                ],
            },
            {
                "id": "fresh",
                "title": "新歌探索",
                "subtitle": "来自 iTunes 的歌单外候选，点击交给 QQ 音乐搜索",
                "intent": "fresh",
                "recommendations": [
                    _recommendation_card(
                        song,
                        reason="iTunes 新候选：不在当前歌单里，但和你的口味种子有可解释的相邻关系。",
                        confidence=max(0.48, 0.70 - index * 0.04),
                    )
                    for index, song in enumerate(fresh_songs)
                ],
            },
            {
                "id": "edge",
                "title": "边界尝试",
                "subtitle": "更冒险的相邻方向，用来发现你可能没主动搜过的东西",
                "intent": "edge",
                "recommendations": [
                    {
                        **_recommendation_card(
                            song,
                            reason="风险探索：保留部分当前口味线索，但刻意推远一点。",
                            confidence=max(0.38, 0.58 - index * 0.03),
                        ),
                        "is_exploratory": True,
                    }
                    for index, song in enumerate(edge_songs)
                ],
            },
        ],
    }


async def _fast_recommendations(message: str, limit: int = 5) -> Optional[dict]:
    """Fast local recommendation path for the CSV-only library.

    The full Agent path waits for LLM tool planning and judging. For the current
    local-only library, direct vector retrieval gives useful cards in seconds.
    """
    query = message.strip()
    if not query:
        return None

    store = _get_store()
    songs = store.get_all_songs()
    if not songs:
        return None

    try:
        results = _get_vector_store().search(query, n_results=limit)
        rec_songs = [store.get_song(r["id"]) for r in results]
        rec_songs = [song for song in rec_songs if song]
    except Exception as exc:
        logger.warning("Fast vector recommendation failed, falling back to keyword search: %s", exc)
        rec_songs = store.search_songs(query, limit=limit)

    local_limit = min(3, limit)
    recommendations = []
    if rec_songs:
        recommendations = [
            _recommendation_card(
                song,
                reason=(
                    f"和「{query}」的氛围接近"
                    + (f"，来自 {', '.join(song.tags[:2])}" if song.tags else "")
                ),
                confidence=max(0.45, 0.78 - index * 0.05),
            )
            for index, song in enumerate(rec_songs[:local_limit])
        ]

    recommendations.extend(await _external_recommendations(query, limit=limit - len(recommendations)))

    if not recommendations:
        return None

    external_count = sum(
        1
        for rec in recommendations
        if rec["song"]["id"] < 0 and "iTunes" in rec["song"].get("tags", [])
    )
    if external_count == len(recommendations):
        response = "我这次主要从外部候选池扩展了几首新歌；这些不是你当前歌单里的歌，播放建议先用 QQ 音乐搜索。"
    elif external_count:
        response = "我先给 3 首本地高置信匹配，再追加几首 iTunes 外部发现，方便你听到没在当前歌单里的东西。"
    else:
        response = "我先按你的本地歌单和当前 taste profile 快速找了这几首。iTunes 外部发现暂时没有返回合适的新候选。"

    return {
        "response": response,
        "recommendations": recommendations,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Melodia", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8765"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def warm_recommendation_index():
        def warm():
            try:
                _get_vector_store().search("warmup", n_results=1)
                logger.info("Recommendation index warmed")
            except Exception as exc:
                logger.warning("Recommendation index warmup failed: %s", exc)

        threading.Thread(target=warm, daemon=True).start()

    # --- Chat ---

    @app.get("/api/discovery/feed")
    async def discovery_feed(q: str = ""):
        return await _discovery_feed(q)

    @app.post("/api/discovery/feed")
    async def discovery_feed_post(request: DiscoveryRequest):
        return await _discovery_feed(request.query)

    @app.post("/api/chat")
    async def chat(request: ChatRequest):
        fast = await _fast_recommendations(request.message)
        if fast:
            return {
                **fast,
                "session_id": request.session_id,
            }

        agent = _get_agent()
        tool_executor = _get_tool_executor()
        response = await agent.chat(request.message)
        return {
            "response": response,
            "recommendations": tool_executor.consume_recent_recommendations(),
            "session_id": request.session_id,
        }

    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket):
        await websocket.accept()
        agent = _get_agent()

        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                user_message = msg.get("message", "")

                response = await agent.chat(user_message)
                recommendations = _get_tool_executor().consume_recent_recommendations()
                await websocket.send_json({
                    "type": "response",
                    "content": response,
                    "recommendations": recommendations,
                })
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")

    # --- Player ---

    @app.post("/api/player/play")
    async def play_song(request: PlayRequest):
        store = _get_store()
        song = store.get_song(request.song_id)
        if request.song_id <= 0:
            return {
                "action": "open_url",
                "provider": "qqmusic",
                "url": qq_music_search_url(song) if song else "https://y.qq.com/",
                "open_url": qq_music_search_url(song) if song else "https://y.qq.com/",
                "message": "Opening QQ Music search. Playback is handled by QQ Music.",
                "song": _song_payload(song) if song else {"id": request.song_id},
            }

        from ..pipeline.netease_client import NeteaseClient
        config = _get_config()
        client = NeteaseClient(config.netease)
        result = await client.song_url(request.song_id)
        url_data = result.get("data", [{}])
        await client.aclose()
        if url_data and url_data[0].get("url"):
            return {
                "url": url_data[0]["url"],
                "song": {
                    "id": request.song_id,
                    "title": song.title if song else "",
                    "artist": song.artist if song else "",
                    "album": song.album if song else "",
                    "duration_ms": song.duration_ms if song else 0,
                },
            }
        if song:
            return {
                "action": "open_url",
                "provider": "qqmusic",
                "url": qq_music_search_url(song),
                "open_url": qq_music_search_url(song),
                "message": "Netease playback is unavailable. Opening QQ Music search instead.",
                "song": _song_payload(song),
            }
        return {"error": "No playback URL available"}

    # --- Feedback ---

    @app.post("/api/feedback")
    async def submit_feedback(request: FeedbackRequest):
        if request.feedback_type == "dialogue" and request.context:
            _get_feedback_processor().process_dialogue_feedback(request.song_id, request.context)
            return {"status": "recorded"}
        fb = Feedback(
            song_id=request.song_id,
            feedback_type=request.feedback_type,
            context=request.context or "",
        )
        _get_feedback_processor().process_feedback(fb)
        return {"status": "recorded"}

    # --- Songs ---

    @app.get("/api/songs/search")
    async def search_songs(q: str, limit: int = 10):
        store = _get_store()
        songs = store.search_songs(q, limit=limit)
        return {
            "songs": [
                {"id": s.netease_id, "title": s.title, "artist": s.artist,
                 "album": s.album, "genres": s.genres, "tags": s.tags}
                for s in songs
            ]
        }

    @app.get("/api/songs/{song_id}")
    async def get_song(song_id: int):
        store = _get_store()
        song = store.get_song(song_id)
        if not song:
            return {"error": "Song not found"}
        return {
            "id": song.netease_id, "title": song.title, "artist": song.artist,
            "album": song.album, "genres": song.genres, "tags": song.tags,
            "mood": song.mood, "duration_ms": song.duration_ms,
            "tempo": song.tempo, "energy": song.energy, "valence": song.valence,
            "lyrics_excerpt": song.lyrics[:200] if song.lyrics else "",
        }

    # --- Profile ---

    @app.get("/api/profile")
    async def get_profile():
        store = _get_store()
        profile = store.load_taste_profile()
        if not profile:
            return {"error": "Taste profile not generated yet"}
        return {
            "narrative": profile.narrative,
            "top_genres": profile.top_genres,
            "top_artists": profile.top_artists,
            "anti_patterns": profile.anti_patterns,
            "dimension_insights": profile.dimension_insights,
            "song_count": profile.song_count,
            "interaction_count": profile.interaction_count,
        }

    # --- Status ---

    @app.get("/api/status")
    async def status():
        store = _get_store()
        songs = store.get_all_songs()
        return {
            "total_songs": len(songs),
            "matched_songs": sum(1 for s in songs if s.netease_id > 0),
            "external_candidates": sum(1 for s in songs if s.netease_id < 0 and "iTunes" in s.tags),
            "songs_with_features": sum(1 for s in songs if s.has_audio_features),
            "favorites": sum(1 for s in songs if s.is_favorite),
        }

    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app
