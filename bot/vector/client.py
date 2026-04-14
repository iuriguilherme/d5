"""ChromaDB VectorStore wrapper.

All ChromaDB calls are synchronous — they must be wrapped in asyncio.to_thread()
to avoid blocking the event loop.
"""
import asyncio
from functools import partial
from pathlib import Path

import chromadb


class VectorStore:
    def __init__(self, chroma_path: Path) -> None:
        chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_path))

    # ── Collection helpers ────────────────────────────────────────────────────

    def _subject_collection(self, user_id: int):
        return self._client.get_or_create_collection(
            f"subject_embeddings_{user_id}",
            metadata={"hnsw:space": "cosine"},
        )

    def _strategy_collection(self, user_id: int):
        return self._client.get_or_create_collection(
            f"strategy_embeddings_{user_id}",
            metadata={"hnsw:space": "cosine"},
        )

    # ── Subject embeddings ────────────────────────────────────────────────────

    async def upsert_subject(
        self,
        user_id: int,
        subject_id: str,
        embedding: list[float],
        metadata: dict | None = None,
    ) -> None:
        def _sync():
            col = self._subject_collection(user_id)
            # ChromaDB rejects empty metadata dicts; pass None when no metadata
            col.upsert(
                ids=[subject_id],
                embeddings=[embedding],
                metadatas=[metadata] if metadata else None,
            )

        await asyncio.to_thread(_sync)

    async def get_subject_embedding(
        self, user_id: int, subject_id: str
    ) -> list[float] | None:
        def _sync():
            col = self._subject_collection(user_id)
            result = col.get(ids=[subject_id], include=["embeddings"])
            embeddings = result.get("embeddings")
            # embeddings may be a numpy array — check length, not truthiness
            if embeddings is not None and len(embeddings) > 0:
                return list(embeddings[0])
            return None

        return await asyncio.to_thread(_sync)

    async def query_similar_subjects(
        self,
        user_id: int,
        embedding: list[float],
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """Return up to n_results subjects sorted by cosine similarity."""

        def _sync():
            col = self._subject_collection(user_id)
            count = col.count()
            if count == 0:
                return []
            kwargs: dict = {
                "query_embeddings": [embedding],
                "n_results": min(n_results, count),
                "include": ["metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
            result = col.query(**kwargs)
            ids = result["ids"][0]
            distances = result["distances"][0]
            metadatas = result["metadatas"][0]
            return [
                {"id": i, "distance": d, "metadata": m}
                for i, d, m in zip(ids, distances, metadatas)
            ]

        return await asyncio.to_thread(_sync)

    async def delete_subject(self, user_id: int, subject_id: str) -> None:
        def _sync():
            col = self._subject_collection(user_id)
            col.delete(ids=[subject_id])

        await asyncio.to_thread(_sync)

    # ── Strategy embeddings ───────────────────────────────────────────────────

    async def upsert_strategy(
        self,
        user_id: int,
        note_id: str,
        embedding: list[float],
        metadata: dict | None = None,
    ) -> None:
        def _sync():
            col = self._strategy_collection(user_id)
            col.upsert(
                ids=[note_id],
                embeddings=[embedding],
                metadatas=[metadata] if metadata else None,
            )

        await asyncio.to_thread(_sync)

    async def query_strategy_alignment(
        self,
        user_id: int,
        subject_embedding: list[float],
        n_results: int = 10,
    ) -> list[dict]:
        """Return strategy note distances for the given subject embedding."""

        def _sync():
            col = self._strategy_collection(user_id)
            count = col.count()
            if count == 0:
                return []
            result = col.query(
                query_embeddings=[subject_embedding],
                n_results=min(n_results, count),
                include=["distances"],
            )
            ids = result["ids"][0]
            distances = result["distances"][0]
            return [{"id": i, "distance": d} for i, d in zip(ids, distances)]

        return await asyncio.to_thread(_sync)
