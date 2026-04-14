"""Tests for ChromaDB VectorStore wrapper."""
import math

import pytest

from bot.vector.client import VectorStore


@pytest.fixture
def vector_store(tmp_path):
    return VectorStore(chroma_path=tmp_path / "chroma")


def _unit_vec(dim: int = 384, val: float = 1.0) -> list[float]:
    """Return a unit-normalized vector."""
    v = [val] + [0.0] * (dim - 1)
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def _vec(dims: list[float]) -> list[float]:
    """Return a normalized vector from a short spec, padded to 384."""
    padded = dims + [0.0] * (384 - len(dims))
    norm = math.sqrt(sum(x * x for x in padded)) or 1.0
    return [x / norm for x in padded]


USER = 42


# ── Subject collection ────────────────────────────────────────────────────────


async def test_upsert_then_get(vector_store):
    emb = _unit_vec()
    await vector_store.upsert_subject(USER, "sub-1", emb, {"text": "cooking"})
    result = await vector_store.get_subject_embedding(USER, "sub-1")
    assert result is not None
    assert len(result) == 384


async def test_get_missing_returns_none(vector_store):
    result = await vector_store.get_subject_embedding(USER, "nonexistent")
    assert result is None


async def test_query_similar_subjects_empty(vector_store):
    result = await vector_store.query_similar_subjects(USER, _unit_vec())
    assert result == []


async def test_query_similar_subjects_nearest_first(vector_store):
    # Two embeddings: one identical to query, one orthogonal
    identical = _vec([1.0])
    orthogonal = _vec([0.0, 1.0])
    query = _vec([1.0])

    await vector_store.upsert_subject(USER, "identical", identical)
    await vector_store.upsert_subject(USER, "orthogonal", orthogonal)

    results = await vector_store.query_similar_subjects(USER, query, n_results=2)
    assert len(results) == 2
    # Cosine distance: identical should have smaller distance
    assert results[0]["id"] == "identical"
    assert results[0]["distance"] < results[1]["distance"]


async def test_upsert_idempotent(vector_store):
    emb = _unit_vec()
    await vector_store.upsert_subject(USER, "sub-x", emb)
    await vector_store.upsert_subject(USER, "sub-x", emb)  # should not raise
    result = await vector_store.get_subject_embedding(USER, "sub-x")
    assert result is not None


# ── Strategy collection ───────────────────────────────────────────────────────


async def test_upsert_strategy_then_query_alignment(vector_store):
    strategy_emb = _vec([1.0])
    subject_emb = _vec([1.0])  # identical → distance ≈ 0

    await vector_store.upsert_strategy(USER, "note-1", strategy_emb)
    results = await vector_store.query_strategy_alignment(USER, subject_emb)

    assert len(results) == 1
    assert results[0]["id"] == "note-1"
    # Cosine distance ≈ 0 for identical vectors
    assert results[0]["distance"] < 0.05


async def test_query_strategy_alignment_empty(vector_store):
    results = await vector_store.query_strategy_alignment(USER, _unit_vec())
    assert results == []


async def test_collections_are_isolated(vector_store):
    """Subject and strategy collections must not cross-contaminate."""
    emb = _unit_vec()
    await vector_store.upsert_subject(USER, "sub-1", emb)

    # Strategy collection should still be empty
    strategy_results = await vector_store.query_strategy_alignment(USER, emb)
    assert strategy_results == []
