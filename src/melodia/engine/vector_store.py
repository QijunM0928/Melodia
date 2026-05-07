"""Vector store and embedding management using ChromaDB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ..models.song import Song
from ..models.store import Store

logger = logging.getLogger(__name__)

DEFAULT_CHROMA_PATH = Path.home() / ".melodia" / "chromadb"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


class VectorStore:
    """ChromaDB-backed vector store for song metadata embeddings."""

    def __init__(self, persist_dir: Path = DEFAULT_CHROMA_PATH):
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None
        self._encoder = None

    def _get_encoder(self):
        """Lazy-load the sentence-transformers model."""
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            self._encoder = SentenceTransformer(EMBEDDING_MODEL)
        return self._encoder

    def _get_collection(self):
        """Lazy-load ChromaDB collection."""
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = self._client.get_or_create_collection(
                name="songs",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def index_song(self, song: Song):
        """Add or update a single song in the vector index."""
        if not song.netease_id:
            return

        encoder = self._get_encoder()
        collection = self._get_collection()

        doc_id = str(song.netease_id)
        embedding = encoder.encode(song.search_text).tolist()

        metadata = {
            "title": song.title,
            "artist": song.artist,
            "album": song.album or "",
            "genres": ", ".join(song.genres[:5]) if song.genres else "",
            "mood": song.mood or "",
            "tempo": song.tempo,
            "energy": song.energy,
            "valence": song.valence,
            "danceability": song.danceability,
            "acousticness": song.acousticness,
            "brightness": song.brightness,
        }

        # Upsert (add or update)
        collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[song.search_text],
            metadatas=[metadata],
        )
        song.embedding_id = doc_id

    def index_all(self, store: Store):
        """Index all songs from the SQLite store."""
        songs = store.get_all_songs()
        encoder = self._get_encoder()
        collection = self._get_collection()

        logger.info(f"Indexing {len(songs)} songs...")

        # Batch encode
        texts = [s.search_text for s in songs if s.netease_id]
        ids = [str(s.netease_id) for s in songs if s.netease_id]
        embeddings = encoder.encode(texts).tolist()

        metadatas = []
        for s in songs:
            if not s.netease_id:
                continue
            metadatas.append({
                "title": s.title,
                "artist": s.artist,
                "album": s.album or "",
                "genres": ", ".join(s.genres[:5]) if s.genres else "",
                "mood": s.mood or "",
                "tempo": s.tempo,
                "energy": s.energy,
                "valence": s.valence,
                "danceability": s.danceability,
                "acousticness": s.acousticness,
                "brightness": s.brightness,
            })

        # Batch upsert (ChromaDB handles batching internally)
        for i in range(0, len(ids), 100):
            batch_ids = ids[i:i+100]
            batch_embeddings = embeddings[i:i+100]
            batch_docs = texts[i:i+100]
            batch_meta = metadatas[i:i+100]
            collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                documents=batch_docs,
                metadatas=batch_meta,
            )

        # Update embedding_ids in SQLite
        for s in songs:
            if s.netease_id:
                s.embedding_id = str(s.netease_id)
                store.upsert_song(s)

        logger.info(f"Indexed {len(ids)} songs in ChromaDB")

    def search(
        self,
        query: str,
        n_results: int = 15,
        where: Optional[dict] = None,
        exclude_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Search songs by natural language query.

        Returns list of dicts with: id, document, metadata, distance.
        """
        encoder = self._get_encoder()
        collection = self._get_collection()

        query_embedding = encoder.encode(query).tolist()

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        if not results["ids"][0]:
            return []

        songs = []
        for i, doc_id in enumerate(results["ids"][0]):
            if exclude_ids and doc_id in exclude_ids:
                continue
            songs.append({
                "id": int(doc_id),
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
        return songs

    def get_embedding(self, song_id: int) -> Optional[list[float]]:
        """Get the stored embedding for a song."""
        collection = self._get_collection()
        result = collection.get(ids=[str(song_id)], include=["embeddings"])
        if result["embeddings"]:
            return result["embeddings"][0]
        return None

    def compute_centroid(self, song_ids: list[int]) -> list[float]:
        """Compute the centroid (average) embedding for a set of songs."""
        import numpy as np

        collection = self._get_collection()
        ids = [str(id) for id in song_ids]
        result = collection.get(ids=ids, include=["embeddings"])

        if not result["embeddings"]:
            return []

        embeddings = np.array(result["embeddings"])
        centroid = embeddings.mean(axis=0)
        centroid = centroid / np.linalg.norm(centroid)
        return centroid.tolist()
