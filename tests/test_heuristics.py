"""Isolated heuristic tests — verify each heuristic's scoring logic."""
import math
import random
from datetime import datetime, timedelta, timezone

from bot.heuristics.cooldown import cooldown
from bot.heuristics.jitter import jitter
from bot.heuristics.novelty import novelty
from bot.heuristics.platform_fit import platform_fit
from bot.heuristics.recency import recency
from bot.heuristics.registry import HeuristicRegistry, SuggestionContext, WEIGHT_VALUES
from bot.heuristics.strategy_align import strategy_align
from bot.models import Subject
from bot.models.heuristic_profile import DEFAULT_HEURISTIC_CONFIG
from bot.models.subject import SubjectSource, SubjectStatus

NOW = datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc)


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


def _sub(days_since: int | None = None) -> Subject:
    s = Subject(
        user_id=1,
        text="test",
        source=SubjectSource.manual,
        status=SubjectStatus.active,
    )
    if days_since is not None:
        s.last_posted_at = NOW - timedelta(days=days_since)
    return s


# ── cooldown ──────────────────────────────────────────────────────────────────

def test_cooldown_inside_window(): assert cooldown(_sub(3), _ctx()) == -math.inf
def test_cooldown_outside_window(): assert cooldown(_sub(20), _ctx()) == 0.0
def test_cooldown_at_boundary(): assert cooldown(_sub(14), _ctx()) == 0.0  # == not <
def test_cooldown_never_posted(): assert cooldown(_sub(), _ctx()) == 0.0
def test_cooldown_naive_datetime():
    s = _sub()
    s.last_posted_at = NOW.replace(tzinfo=None) - timedelta(days=3)
    assert cooldown(s, _ctx()) == -math.inf


# ── recency ───────────────────────────────────────────────────────────────────

def test_recency_never_posted_bonus(): assert recency(_sub(), _ctx()) == 0.2
def test_recency_bounds():
    assert 0.0 <= recency(_sub(1), _ctx()) <= 1.0
    assert 0.0 <= recency(_sub(365), _ctx()) <= 1.0
def test_recency_monotonic():
    scores = [recency(_sub(d), _ctx()) for d in [1, 7, 14, 30, 90]]
    assert all(scores[i] < scores[i + 1] for i in range(len(scores) - 1))


# ── novelty ───────────────────────────────────────────────────────────────────

def test_novelty_never_posted(): assert novelty(_sub(), _ctx()) == 1.0
def test_novelty_posted(): assert novelty(_sub(5), _ctx()) == 0.0


# ── strategy_align ────────────────────────────────────────────────────────────

def test_strategy_align_empty(): assert strategy_align(_sub(), _ctx()) == 0.0
def test_strategy_align_perfect_match():
    ctx = _ctx(strategy_embeddings=[{"id": "n", "distance": 0.0}])
    assert abs(strategy_align(_sub(), ctx) - 1.0) < 1e-9
def test_strategy_align_orthogonal():
    ctx = _ctx(strategy_embeddings=[{"id": "n", "distance": 2.0}])
    assert strategy_align(_sub(), ctx) == 0.0
def test_strategy_align_average():
    ctx = _ctx(strategy_embeddings=[{"id": "a", "distance": 0.0}, {"id": "b", "distance": 1.0}])
    assert abs(strategy_align(_sub(), ctx) - 0.75) < 1e-9


# ── platform_fit ──────────────────────────────────────────────────────────────

def test_platform_fit_neutral(): assert platform_fit(_sub(), _ctx()) == 0.5


# ── jitter ────────────────────────────────────────────────────────────────────

def test_jitter_bounds():
    for _ in range(100):
        val = jitter(_sub(), _ctx())
        assert -0.05 <= val <= 0.05


# ── HeuristicRegistry ─────────────────────────────────────────────────────────

def test_registry_get_enabled_off_weight():
    reg = HeuristicRegistry()
    reg.register("my_h", lambda s, c: 1.0)
    config = {"my_h": "off"}
    enabled = reg.get_enabled(config)
    assert len(enabled) == 0


def test_registry_weight_values():
    assert WEIGHT_VALUES["off"] == 0.0
    assert WEIGHT_VALUES["low"] < WEIGHT_VALUES["medium"] < WEIGHT_VALUES["high"]
