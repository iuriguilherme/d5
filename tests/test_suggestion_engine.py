"""Tests for SuggestionEngine and heuristics pipeline."""
import math
import random
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bot.heuristics.cooldown import cooldown
from bot.heuristics.novelty import novelty
from bot.heuristics.recency import recency
from bot.heuristics.registry import HeuristicRegistry, SuggestionContext
from bot.heuristics.strategy_align import strategy_align
from bot.models import HeuristicProfile, Subject, User
from bot.models.heuristic_profile import DEFAULT_HEURISTIC_CONFIG
from bot.models.subject import SubjectSource, SubjectStatus
from bot.services.suggestion import NoSubjectAvailableError, SuggestionEngine


# ── Fixtures ──────────────────────────────────────────────────────────────────


NOW = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)


def _ctx(**kwargs) -> SuggestionContext:
    defaults = {
        "user_id": 1,
        "cooldown_days": 14,
        "now": NOW,
        "platform_hint": None,
        "strategy_embeddings": [],
        "profile_config": dict(DEFAULT_HEURISTIC_CONFIG),
    }
    defaults.update(kwargs)
    return SuggestionContext(**defaults)


def _subject(days_since_posted: int | None = None) -> Subject:
    sub = Subject(
        user_id=1,
        text="test subject",
        source=SubjectSource.manual,
        status=SubjectStatus.active,
    )
    if days_since_posted is not None:
        sub.last_posted_at = NOW - timedelta(days=days_since_posted)
    return sub


# ── Individual heuristics ─────────────────────────────────────────────────────


def test_cooldown_hard_excludes_within_window():
    sub = _subject(days_since_posted=3)
    ctx = _ctx(cooldown_days=14)
    assert cooldown(sub, ctx) == -math.inf


def test_cooldown_passes_outside_window():
    sub = _subject(days_since_posted=20)
    ctx = _ctx(cooldown_days=14)
    assert cooldown(sub, ctx) == 0.0


def test_cooldown_never_posted_passes():
    sub = _subject()
    ctx = _ctx()
    assert cooldown(sub, ctx) == 0.0


def test_recency_never_posted_bonus():
    sub = _subject()
    assert recency(sub, _ctx()) == 0.2


def test_recency_rises_with_time():
    short_ago = recency(_subject(days_since_posted=1), _ctx())
    long_ago = recency(_subject(days_since_posted=30), _ctx())
    assert long_ago > short_ago


def test_novelty_never_posted_returns_one():
    assert novelty(_subject(), _ctx()) == 1.0


def test_novelty_posted_returns_zero():
    assert novelty(_subject(days_since_posted=5), _ctx()) == 0.0


def test_strategy_align_no_notes_returns_zero():
    assert strategy_align(_subject(), _ctx(strategy_embeddings=[])) == 0.0


def test_strategy_align_with_notes():
    # distance=0.0 → similarity=1.0; distance=1.0 → similarity=0.5
    ctx = _ctx(strategy_embeddings=[{"id": "n1", "distance": 0.0}, {"id": "n2", "distance": 1.0}])
    score = strategy_align(_subject(), ctx)
    assert abs(score - 0.75) < 1e-6


# ── SuggestionEngine ──────────────────────────────────────────────────────────


def _build_engine(subjects: list[Subject], profile_config: dict | None = None) -> SuggestionEngine:
    """Build SuggestionEngine with a mock session returning the given subjects."""
    from bot.services.suggestion import build_default_registry

    user = User(user_id=1, cooldown_days=14)
    profile = HeuristicProfile(
        user_id=1, config=profile_config or dict(DEFAULT_HEURISTIC_CONFIG)
    )

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(
        side_effect=[
            # First call: subjects
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=subjects)))),
            # Second call: heuristic profile
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=profile)))),
        ]
    )
    mock_session.get = AsyncMock(return_value=user)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session

    mock_store = MagicMock()
    mock_store.query_strategy_alignment = AsyncMock(return_value=[])

    settings = MagicMock()
    settings.cooldown_days = 14

    return SuggestionEngine(
        settings=settings,
        session_factory=mock_factory,
        vector_store=mock_store,
        registry=build_default_registry(),
    )


async def test_suggest_returns_subject():
    sub = _subject(days_since_posted=30)
    engine = _build_engine([sub])
    result = await engine.suggest(user_id=1)
    assert result is sub


async def test_suggest_empty_pool_raises():
    engine = _build_engine([])
    with pytest.raises(NoSubjectAvailableError):
        await engine.suggest(user_id=1)


async def test_suggest_all_in_cooldown_raises():
    subs = [_subject(days_since_posted=3), _subject(days_since_posted=5)]
    engine = _build_engine(subs)
    with pytest.raises(NoSubjectAvailableError, match="cooldown"):
        await engine.suggest(user_id=1)


async def test_suggest_cooldown_excludes_recent_subject():
    recent = _subject(days_since_posted=3)
    recent.text = "too recent"
    old = _subject(days_since_posted=20)
    old.text = "old enough"
    engine = _build_engine([recent, old])
    result = await engine.suggest(user_id=1)
    assert result is old


async def test_suggest_high_novelty_scores_higher():
    """Never-posted subject should score higher than posted subject (all else equal)."""
    never = _subject()
    posted = _subject(days_since_posted=20)
    # Run many times with deterministic seed to avoid epsilon-greedy flips
    random.seed(42)
    wins = 0
    for _ in range(50):
        engine = _build_engine([never, posted])
        result = await engine.suggest(user_id=1)
        if result is never:
            wins += 1
    assert wins > 30, f"never-posted won only {wins}/50 — expected >30"


async def test_suggest_exclude_ids():
    sub1 = _subject(days_since_posted=30)
    sub1.subject_id = uuid4()
    sub2 = _subject(days_since_posted=25)
    sub2.subject_id = uuid4()

    engine = _build_engine([sub2])  # sub1 excluded → engine only sees sub2
    result = await engine.suggest(user_id=1, exclude_ids=[sub1.subject_id])
    assert result is sub2
