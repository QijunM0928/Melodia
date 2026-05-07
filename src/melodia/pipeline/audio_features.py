"""Audio feature extraction using librosa."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from ..models.song import Song
from ..config import NeteaseConfig

logger = logging.getLogger(__name__)


def extract_features(audio_path: str | Path) -> dict:
    """Extract audio features from a local audio file using librosa.

    Returns dict with: tempo, energy, valence_proxy, danceability,
    acousticness, brightness, key, mode.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(audio_path, sr=22050, duration=30)

    # Tempo (BPM)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    if isinstance(tempo, np.ndarray):
        tempo = float(tempo[0]) if tempo.size > 0 else 0.0
    else:
        tempo = float(tempo)

    # RMS energy (0-1 normalized)
    rms = float(librosa.feature.rms(y=y).mean())
    energy = min(rms * 10, 1.0)  # rough normalization

    # Spectral centroid → brightness (Hz, higher = brighter)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    brightness = float(centroid.mean())

    # Valence proxy: spectral contrast variance (more variance → more "major/happy" feel)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    valence = float(np.clip(contrast.var() / 20, 0, 1))

    # Danceability proxy: beat strength + regularity
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)[1]
    if len(beat_frames) > 2:
        beat_intervals = np.diff(beat_frames).astype(float)
        regularity = 1.0 - min(float(np.std(beat_intervals) / (np.mean(beat_intervals) + 1e-6)), 1.0)
        danceability = float(np.clip(regularity * 0.7 + energy * 0.3, 0, 1))
    else:
        danceability = 0.0

    # Acousticness: spectral flatness (higher = more noise/electric, lower = more tonal/acoustic)
    flatness = librosa.feature.spectral_flatness(y=y)
    acousticness = float(np.clip(1.0 - flatness.mean() * 100, 0, 1))

    # Key and mode
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key_profile = chroma.sum(axis=1)
    key = int(np.argmax(key_profile))  # 0=C, 1=C#, ..., 11=B

    # Mode: major vs minor (Krumhansl-Schmuckler key-finding simplified)
    major_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    minor_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    major_corr = float(np.corrcoef(key_profile, major_profile)[0, 1]) if len(key_profile) == 12 else 0
    minor_corr = float(np.corrcoef(key_profile, minor_profile)[0, 1]) if len(key_profile) == 12 else 0
    mode = 1 if major_corr > minor_corr else 0

    return {
        "tempo": round(tempo, 1),
        "energy": round(energy, 3),
        "valence": round(valence, 3),
        "danceability": round(danceability, 3),
        "acousticness": round(acousticness, 3),
        "brightness": round(brightness, 1),
        "key": key,
        "mode": mode,
    }


async def download_preview(netease_id: int, config: NeteaseConfig) -> Optional[Path]:
    """Download a 30s preview from Netease for feature extraction."""
    base_url = config.base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        # Get song URL
        headers = {}
        if config.cookie:
            headers["Cookie"] = config.cookie
        resp = await client.get(
            f"{base_url}/song/url/v1",
            params={"id": netease_id, "level": "standard"},
            headers=headers,
        )
        data = resp.json()
        url = data.get("data", [{}])[0].get("url")
        if not url:
            return None

        # Download audio
        audio_resp = await client.get(url, follow_redirects=True)
        if audio_resp.status_code != 200:
            return None

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(audio_resp.content)
        tmp.close()
        return Path(tmp.name)


async def extract_for_song(song: Song, config: NeteaseConfig) -> Song:
    """Download preview and extract audio features for a song."""
    if song.has_audio_features:
        return song

    if not song.netease_id:
        logger.debug(f"Skipping feature extraction (no netease_id): {song.title}")
        return song

    path = await download_preview(song.netease_id, config)
    if not path:
        logger.debug(f"Could not download preview for: {song.title}")
        return song

    try:
        features = extract_features(path)
        song.tempo = features["tempo"]
        song.energy = features["energy"]
        song.valence = features["valence"]
        song.danceability = features["danceability"]
        song.acousticness = features["acousticness"]
        song.brightness = features["brightness"]
        song.key = features["key"]
        song.mode = features["mode"]
    except Exception as e:
        logger.warning(f"Feature extraction failed for '{song.title}': {e}")
    finally:
        path.unlink(missing_ok=True)

    return song
