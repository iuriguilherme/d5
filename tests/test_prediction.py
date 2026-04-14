"""Tests for PredictionService — embedding and clustering."""
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.config import Settings
from bot.vector.client import VectorStore


@pytest.fixture
def mock_model():
    """Mock SentenceTransformer that returns deterministic normalized embeddings."""
    import numpy as np

    model = MagicMock()

    def _encode(texts, normalize_embeddings=True):
        # Return a unit vector per text; different for each unique text
        result = []
        for t in texts:
            v = [float(len(t) % 10 + 1)] + [0.0] * 383
            norm = math.sqrt(sum(x * x for x in v))
            result.append([x / norm for x in v])
        return np.array(result)

    model.encode = _encode
    return model


@pytest.fixture
def prediction_svc(settings, tmp_path, mock_model):
    from bot.services.prediction import PredictionService

    store = VectorStore(chroma_path=tmp_path / "chroma")

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        svc = PredictionService(settings=settings, vector_store=store)
    return svc, store


# ── embed_text ────────────────────────────────────────────────────────────────


async def test_embed_text_returns_384_floats(prediction_svc):
    svc, _ = prediction_svc
    emb = await svc.embed_text("cooking video ideas")
    assert isinstance(emb, list)
    assert len(emb) == 384


async def test_embed_text_is_unit_normalized(prediction_svc):
    svc, _ = prediction_svc
    emb = await svc.embed_text("cooking video ideas")
    norm = math.sqrt(sum(x * x for x in emb))
    assert abs(norm - 1.0) < 1e-5


# ── cluster_import ────────────────────────────────────────────────────────────


async def test_cluster_import_sparse_skips(prediction_svc, db_session, settings):
    """Fewer posts than min_samples → no clustering, no error."""
    svc, _ = prediction_svc

    from unittest.mock import MagicMock, AsyncMock
    from bot.models import User, Post, ImportBatch
    from bot.models.post import PostPlatform, PostSource
    from datetime import datetime, timezone
    from uuid import uuid4

    user = User(user_id=1)
    db_session.add(user)
    await db_session.flush()

    # Add fewer posts than min_samples (default=2 means 0 or 1 posts skips)
    # With min_samples=2, we need fewer than 2 non-empty posts
    post = Post(
        user_id=1,
        platform=PostPlatform.instagram,
        source="imported",
        posted_at=datetime.now(timezone.utc),
        caption_excerpt="single post",
    )
    db_session.add(post)
    await db_session.flush()

    mock_factory = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory.return_value = mock_ctx

    # settings.dbscan_min_samples=2 → 1 post skips
    count = await svc.cluster_import(user_id=1, batch_id=uuid4(), session_factory=mock_factory)
    assert count == 0


async def test_cluster_import_creates_pending_subject(prediction_svc, tmp_path, settings):
    """10 posts in 2 clusters → gap topics created as pending_approval subjects."""
    import numpy as np
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    from bot.models import Post, Subject, User
    from bot.models.post import PostPlatform
    from bot.models.subject import SubjectStatus
    from bot.services.prediction import PredictionService
    from bot.vector.client import VectorStore

    store = VectorStore(chroma_path=tmp_path / "chroma2")

    # Model that creates 2 tight clusters: texts with "food" and texts with "travel"
    model = MagicMock()

    def _encode(texts, normalize_embeddings=True):
        result = []
        for t in texts:
            if "food" in t:
                v = [1.0] + [0.0] * 383
            else:
                v = [0.0, 1.0] + [0.0] * 382
            norm = math.sqrt(sum(x * x for x in v))
            result.append([x / norm for x in v])
        return np.array(result)

    model.encode = _encode

    with patch("sentence_transformers.SentenceTransformer", return_value=model):
        svc = PredictionService(settings=settings, vector_store=store)

    # 5 food posts + 5 travel posts
    food_posts = [
        MagicMock(user_id=1, caption_excerpt=f"food dish {i}", source="imported")
        for i in range(5)
    ]
    travel_posts = [
        MagicMock(user_id=1, caption_excerpt=f"travel destination {i}", source="imported")
        for i in range(5)
    ]
    all_posts = food_posts + travel_posts

    from sqlalchemy.ext.asyncio import AsyncSession
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=all_posts))))
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    # Patch subject_id so embedding_id can be set
    with patch("bot.services.prediction.Subject") as MockSubject:
        mock_sub = MagicMock()
        mock_sub.subject_id = uuid4()
        MockSubject.return_value = mock_sub

        mock_factory = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        count = await svc.cluster_import(
            user_id=1, batch_id=uuid4(), session_factory=mock_factory
        )

    # Two distinct clusters → 2 subjects (no existing subjects in Chroma → both are gaps)
    assert count == 2


async def test_cluster_import_skips_covered_topic(prediction_svc, tmp_path, settings):
    """Cluster with close existing subject → no new pending subject created."""
    import numpy as np
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    from bot.services.prediction import PredictionService
    from bot.vector.client import VectorStore

    store = VectorStore(chroma_path=tmp_path / "chroma3")

    model = MagicMock()

    def _encode(texts, normalize_embeddings=True):
        result = []
        for _ in texts:
            result.append([1.0] + [0.0] * 383)
        return np.array(result)

    model.encode = _encode

    with patch("sentence_transformers.SentenceTransformer", return_value=model):
        svc = PredictionService(settings=settings, vector_store=store)

    # Pre-populate Chroma with a very similar subject
    identical_emb = [1.0] + [0.0] * 383
    await store.upsert_subject(1, "existing-sub", identical_emb, {"text": "food"})

    posts = [MagicMock(user_id=1, caption_excerpt=f"food {i}", source="imported") for i in range(5)]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=posts))))
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory.return_value = mock_ctx

    count = await svc.cluster_import(user_id=1, batch_id=uuid4(), session_factory=mock_factory)
    # Existing subject covers the cluster → no new subjects
    assert count == 0
