"""PredictionService — embedding pipeline and DBSCAN clustering.

SentenceTransformer is loaded eagerly at __init__ time to avoid cold-start
latency on the first /suggest or reminder fire. The model is synchronous and
must be wrapped in asyncio.to_thread().
"""
import asyncio
import logging
from typing import TYPE_CHECKING

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.models import Post, Subject
from bot.models.subject import SubjectSource, SubjectStatus
from bot.vector.client import VectorStore

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class PredictionService:
    def __init__(self, settings: Settings, vector_store: VectorStore) -> None:
        self._settings = settings
        self._vector_store = vector_store

        # Eager model load — takes 2–10s on a small VPS; done once at startup
        from sentence_transformers import SentenceTransformer

        self._model: SentenceTransformer = SentenceTransformer(settings.embedding_model)
        logger.info("prediction_model_loaded", model=settings.embedding_model)

    # ── Embedding ──────────────────────────────────────────────────────────────

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string; returns a 384-dim unit-normalized vector."""

        def _sync() -> list[float]:
            # normalize_embeddings=True ensures L2 norm = 1.0 (unit sphere)
            result = self._model.encode([text], normalize_embeddings=True)
            return result[0].tolist()

        return await asyncio.to_thread(_sync)

    # ── Clustering ─────────────────────────────────────────────────────────────

    async def cluster_import(
        self,
        user_id: int,
        batch_id,
        session_factory: async_sessionmaker[AsyncSession],
        bot=None,  # optional: send user notification when predictions are ready
    ) -> int:
        """Cluster imported posts and create pending_approval subjects for gaps.

        Returns the number of new pending_approval subjects created.
        """
        async with session_factory() as session:
            stmt = select(Post).where(
                Post.user_id == user_id,
                Post.source == "imported",
            )
            posts = (await session.execute(stmt)).scalars().all()

        captions = [p.caption_excerpt or "" for p in posts]
        non_empty = [(i, c) for i, c in enumerate(captions) if c.strip()]

        if len(non_empty) < self._settings.dbscan_min_samples:
            logger.info(
                "cluster_import_skipped_sparse",
                user_id=user_id,
                post_count=len(non_empty),
            )
            return 0

        # Embed in batches to avoid OOM on small VPS
        batch_size = 32
        indices = [i for i, _ in non_empty]
        texts = [c for _, c in non_empty]

        def _embed_batch(batch: list[str]) -> np.ndarray:
            return self._model.encode(batch, normalize_embeddings=True)

        embeddings_list = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            emb = await asyncio.to_thread(_embed_batch, batch)
            embeddings_list.append(emb)

        embeddings = np.vstack(embeddings_list)

        # DBSCAN with cosine metric — epsilon=0.3 calibrated in cosine space
        def _cluster(emb: np.ndarray) -> np.ndarray:
            db = DBSCAN(
                eps=self._settings.dbscan_epsilon,
                min_samples=self._settings.dbscan_min_samples,
                metric="cosine",
            )
            return db.fit_predict(emb)

        labels = await asyncio.to_thread(_cluster, embeddings)

        unique_labels = set(labels) - {-1}  # -1 = noise
        if not unique_labels:
            logger.info("cluster_import_no_clusters", user_id=user_id)
            return 0

        created = 0
        async with session_factory() as session:
            for label in unique_labels:
                mask = labels == label
                cluster_embs = embeddings[mask]
                cluster_texts = [texts[i] for i in range(len(texts)) if mask[i]]

                # Centroid = mean of cluster embeddings (already unit-normalized)
                centroid = cluster_embs.mean(axis=0)
                centroid = centroid / (np.linalg.norm(centroid) + 1e-9)

                # Most representative sentence = nearest to centroid
                sims = cluster_embs @ centroid
                rep_idx = int(np.argmax(sims))
                rep_text = cluster_texts[rep_idx]

                # Check if there's already a close subject in the pool
                centroid_list = centroid.tolist()
                neighbors = await self._vector_store.query_similar_subjects(
                    user_id, centroid_list, n_results=1
                )
                if neighbors and neighbors[0]["distance"] < 0.5:
                    # Existing subject covers this cluster — skip
                    continue

                # Gap topic: create pending_approval subject
                subject_text = await self._enrich_label(rep_text)
                subject = Subject(
                    user_id=user_id,
                    text=subject_text,
                    source=SubjectSource.ai_predicted,
                    status=SubjectStatus.pending_approval,
                )
                session.add(subject)
                await session.flush()

                # Store embedding in ChromaDB
                await self._vector_store.upsert_subject(
                    user_id,
                    str(subject.subject_id),
                    centroid_list,
                    {"text": subject_text},
                )
                subject.embedding_id = str(subject.subject_id)
                created += 1

            await session.commit()

        logger.info("cluster_import_done", user_id=user_id, created=created)
        return created

    async def _enrich_label(self, text: str) -> str:
        """Optionally enrich cluster label text via LLM; falls back to raw text."""
        if not self._settings.openai_api_key:
            return text
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._settings.openai_api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Turn this social media post caption into a short content subject "
                            f"idea (5-10 words, no hashtags): {text!r}"
                        ),
                    }
                ],
                max_tokens=30,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("llm_enrichment_failed", error=str(e))
            return text
