"""Recommendation engine — taste-guided search + LLM Judge + Deep-Dive."""

from __future__ import annotations

import logging
from typing import Optional

from ..models.song import Song, Recommendation, DeepDiveResult, TasteProfile
from ..models.store import Store
from ..engine.vector_store import VectorStore
from ..pipeline.netease_client import NeteaseClient
from ..config import NeteaseConfig

logger = logging.getLogger(__name__)


class Recommender:
    """Taste-guided recommendation engine."""

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
        self.netease_client = NeteaseClient(netease_config)
        self.llm_model = llm_model
        self.api_base = api_base
        self.api_key = api_key

    async def recommend_by_vibe(
        self,
        query: str,
        profile: Optional[TasteProfile] = None,
        n_candidates: int = 20,
        n_final: int = 5,
    ) -> list[Recommendation]:
        """Recommend songs by vibe/mood description.

        Pipeline: query enhancement → vector search → profile-weighted ranking → LLM Judge
        """
        # Step 1: Enhance query with taste context
        enhanced_query = query
        if profile and profile.narrative:
            enhanced_query = f"{query}. Context: {profile.narrative_prefix(150)}"

        # Step 2: Vector search
        candidates = self.vector_store.search(enhanced_query, n_results=n_candidates)

        if not candidates:
            # Fallback to Netease search
            return await self._netease_fallback(query, n_final)

        # Step 3: Profile-weighted ranking
        if profile:
            candidates = self._rank_with_profile(candidates, profile)

        # Step 4: Get full Song objects
        songs = []
        for c in candidates[:n_candidates]:
            song = self.store.get_song(c["id"])
            if song:
                songs.append(song)

        # Step 5: LLM Judge (select final n_final with reasons)
        if profile:
            recs = self._llm_judge(query, songs, profile, n_final)
        else:
            recs = [
                Recommendation(song=s, reason="Matched your query", confidence=0.5)
                for s in songs[:n_final]
            ]

        return recs

    async def recommend_similar(
        self,
        song_id: int,
        profile: Optional[TasteProfile] = None,
        n: int = 5,
    ) -> list[Recommendation]:
        """Recommend songs similar to a specific song.

        Uses Netease /simi/song + vector similarity, filtered by taste.
        """
        song = self.store.get_song(song_id)
        if not song:
            return []

        # Combine Netease similar + vector similar
        candidates = []

        # Vector search using song's embedding
        if song.embedding_id:
            vec_results = self.vector_store.search(
                song.search_text, n_results=n * 3,
                exclude_ids=[str(song_id)],
            )
            candidates.extend(vec_results)

        # Netease similar songs
        if song.similar_song_ids:
            for sid in song.similar_song_ids:
                s = self.store.get_song(sid)
                if s:
                    candidates.append({
                        "id": sid,
                        "distance": 0.3,  # moderate similarity from Netease
                        "metadata": {"title": s.title, "artist": s.artist},
                    })

        # Dedup
        seen = {song_id}
        unique = []
        for c in candidates:
            if c["id"] not in seen:
                seen.add(c["id"])
                unique.append(c)

        # Rank with profile
        if profile:
            unique = self._rank_with_profile(unique, profile)

        # Build recommendations
        recs = []
        for c in unique[:n]:
            s = self.store.get_song(c["id"])
            if s:
                recs.append(Recommendation(
                    song=s,
                    reason=f"Similar to {song.title}",
                    confidence=1.0 - c.get("distance", 0.5),
                ))

        return recs

    async def deep_dive(
        self,
        song_id: int,
        profile: Optional[TasteProfile] = None,
        per_dim: int = 3,
    ) -> DeepDiveResult:
        """Multi-dimensional decomposition and exploration of a song.

        Decomposes into 5 dimensions, searches along each.
        """
        song = self.store.get_song(song_id)
        if not song:
            raise ValueError(f"Song {song_id} not found")

        # LLM decomposition
        dimensions = self._decompose_song(song)

        # Search along each dimension
        recs_by_dim = {}
        for dim_name, dim_desc in dimensions.items():
            # Blended query: 60% seed song + 40% dimension focus
            query = f"{song.search_text[:100]} {dim_desc}"
            results = self.vector_store.search(query, n_results=per_dim * 2)

            dim_recs = []
            seen = {song_id}
            for r in results:
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                s = self.store.get_song(r["id"])
                if s:
                    dim_recs.append(Recommendation(
                        song=s,
                        reason=f"{dim_name}: {dim_desc}",
                        confidence=1.0 - r.get("distance", 0.5),
                        matched_dimensions=[dim_name],
                    ))
                if len(dim_recs) >= per_dim:
                    break
            recs_by_dim[dim_name] = dim_recs

        return DeepDiveResult(
            song=song,
            dimensions=dimensions,
            recommendations_by_dim=recs_by_dim,
        )

    def _decompose_song(self, song: Song) -> dict[str, str]:
        """Use LLM to decompose a song into 5 dimensions."""
        import litellm

        prompt = f"""Decompose this song into 5 musical dimensions for exploration.
Each dimension should be a search-worthy description.

Song: {song.title} by {song.artist}
{"Album: " + song.album if song.album else ""}
{"Genre: " + ", ".join(song.genres) if song.genres else ""}
{"Tags: " + ", ".join(song.tags) if song.tags else ""}
{"Tempo: " + f"{song.tempo:.0f} BPM" if song.tempo else ""}
{"Energy: " + f"{song.energy:.2f}" if song.energy else ""}
{"Mood: " + song.mood if song.mood else ""}
{"Lyrics excerpt: " + song.lyrics[:200] if song.lyrics else ""}

Return exactly 5 dimensions as YAML:
```yaml
Production: "description of production style"
Emotion: "emotional quality and arc"
Rhythm: "rhythmic character"
Vocals: "vocal style and quality"
Atmosphere: "overall atmospheric quality"
```"""

        kwargs = {"model": self.llm_model, "temperature": 0.5, "max_tokens": 500}
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = litellm.completion(
            **kwargs,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.choices[0].message.content
        return self._parse_dimensions(text)

    def _parse_dimensions(self, text: str) -> dict[str, str]:
        """Parse dimension descriptions from LLM output."""
        import yaml

        defaults = {
            "Production": "similar production style and texture",
            "Emotion": "similar emotional quality",
            "Rhythm": "similar rhythmic feel",
            "Vocals": "similar vocal style",
            "Atmosphere": "similar atmospheric quality",
        }

        try:
            yaml_text = text
            if "```yaml" in text:
                yaml_text = text.split("```yaml")[1].split("```")[0]
            elif "```" in text:
                yaml_text = text.split("```")[1].split("```")[0]
            data = yaml.safe_load(yaml_text)
            if isinstance(data, dict):
                return {k: str(v) for k, v in data.items() if k in defaults}
        except Exception:
            pass
        return defaults

    def _rank_with_profile(
        self, candidates: list[dict], profile: TasteProfile
    ) -> list[dict]:
        """Re-rank candidates using taste profile.

        Score = pos_sim*0.4 + neg_dist*0.2 + feature_fit*0.3 + recency*0.1
        """
        import numpy as np

        if not profile.positive_centroid:
            return candidates  # No profile data yet

        pos_centroid = np.array(profile.positive_centroid)
        pos_norm = np.linalg.norm(pos_centroid)
        if pos_norm == 0:
            return candidates

        scored = []
        for c in candidates:
            score = 0.0

            # Vector similarity to positive centroid
            emb = self.vector_store.get_embedding(c["id"])
            if emb:
                emb_arr = np.array(emb)
                emb_norm = np.linalg.norm(emb_arr)
                if emb_norm > 0:
                    cos_sim = float(np.dot(pos_centroid, emb_arr) / (pos_norm * emb_norm))
                    score += cos_sim * 0.4

            # Negative centroid distance
            if profile.negative_centroid:
                neg_centroid = np.array(profile.negative_centroid)
                neg_norm = np.linalg.norm(neg_centroid)
                if emb and neg_norm > 0:
                    neg_sim = float(np.dot(neg_centroid, emb_arr) / (neg_norm * emb_norm))
                    score += (1 - neg_sim) * 0.2

            # Audio feature fit
            meta = c.get("metadata", {})
            if profile.audio_feature_distribution and meta.get("tempo"):
                feature_fit = 0.0
                for feat in ["energy", "valence", "danceability", "acousticness"]:
                    feat_dist = profile.audio_feature_distribution.get(feat)
                    feat_val = meta.get(feat, 0)
                    if feat_dist and feat_val:
                        pref_lo = feat_dist.get("preferred_range", [0, 1])[0]
                        pref_hi = feat_dist.get("preferred_range", [0, 1])[1]
                        if pref_lo <= feat_val <= pref_hi:
                            feature_fit += 1.0
                score += (feature_fit / 4) * 0.3

            # Invert distance (lower distance = better)
            score += (1.0 - c.get("distance", 0.5)) * 0.1

            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]

    def _llm_judge(
        self,
        query: str,
        candidates: list[Song],
        profile: TasteProfile,
        n: int = 5,
    ) -> list[Recommendation]:
        """LLM selects final recommendations with explanations."""
        import litellm

        # Format candidates
        songs_text = "\n".join(
            f"{i+1}. {s.title} by {s.artist}"
            f"{' | Genre: ' + ', '.join(s.genres) if s.genres else ''}"
            f"{' | Tags: ' + ', '.join(s.tags[:3]) if s.tags else ''}"
            f"{' | Tempo: ' + f'{s.tempo:.0f}' if s.tempo else ''}"
            f"{' | Energy: ' + f'{s.energy:.2f}' if s.energy else ''}"
            for i, s in enumerate(candidates[:20])
        )

        prompt = f"""You are a music recommendation expert who deeply understands this listener's taste.

LISTENER PROFILE:
{profile.narrative}

ANTI-PATTERNS (avoid these):
{chr(10).join('- ' + p for p in profile.anti_patterns) if profile.anti_patterns else 'None yet'}

USER REQUEST: "{query}"

CANDIDATE SONGS:
{songs_text}

Select the {n} best songs for this listener. For each:
1. Explain WHY it fits (reference specific taste dimensions)
2. Rate confidence (0-1)
3. Mark if it's a "calculated risk" (exploratory pick outside comfort zone)
4. List which taste dimensions it matches

At most 1 song can be a calculated risk.

Return as YAML:
```yaml
recommendations:
  - index: 1
    reason: "..."
    confidence: 0.8
    is_exploratory: false
    matched_dimensions: ["Production", "Emotion"]
```"""

        kwargs = {"model": self.llm_model, "temperature": 0.5, "max_tokens": 1500}
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = litellm.completion(
            **kwargs,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_judge_output(response.choices[0].message.content, candidates)

    def _parse_judge_output(
        self, text: str, candidates: list[Song]
    ) -> list[Recommendation]:
        """Parse LLM Judge output into Recommendation objects."""
        import yaml

        try:
            yaml_text = text
            if "```yaml" in text:
                yaml_text = text.split("```yaml")[1].split("```")[0]
            elif "```" in text:
                yaml_text = text.split("```")[1].split("```")[0]

            data = yaml.safe_load(yaml_text)
            if isinstance(data, dict) and "recommendations" in data:
                recs = []
                for r in data["recommendations"]:
                    idx = r.get("index", 0) - 1
                    if 0 <= idx < len(candidates):
                        recs.append(Recommendation(
                            song=candidates[idx],
                            reason=r.get("reason", ""),
                            confidence=r.get("confidence", 0.5),
                            is_exploratory=r.get("is_exploratory", False),
                            matched_dimensions=r.get("matched_dimensions", []),
                        ))
                return recs
        except Exception:
            logger.warning("Failed to parse LLM Judge output, using top candidates")

        # Fallback: return top candidates without explanations
        return [
            Recommendation(song=s, reason="Top match", confidence=0.5)
            for s in candidates[:5]
        ]

    async def _netease_fallback(
        self, query: str, n: int = 5
    ) -> list[Recommendation]:
        """Fallback: search Netease directly when vector store is empty."""
        result = await self.netease_client.search(query, limit=n)
        songs = result.get("result", {}).get("songs", [])

        recs = []
        for s in songs:
            song = Song(
                title=s.get("name", ""),
                artist=" / ".join(a.get("name", "") for a in s.get("ar", [])),
                album=s.get("al", {}).get("name", ""),
                netease_id=s.get("id", 0),
                netease_song_id=s.get("id", 0),
                duration_ms=s.get("dt", 0),
            )
            recs.append(Recommendation(
                song=song,
                reason=f"Netease search result for '{query}'",
                confidence=0.3,
            ))
        return recs

    async def close(self):
        await self.netease_client.aclose()

    aclose = close
