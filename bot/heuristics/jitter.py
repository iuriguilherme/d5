"""Jitter heuristic — adds small random noise to prevent deterministic ties."""
import random

from bot.heuristics.registry import SuggestionContext
from bot.models import Subject

_JITTER_RANGE = 0.05  # ±5% of the total score range


def jitter(subject: Subject, ctx: SuggestionContext) -> float:
    """Return a small random value in [-0.05, 0.05].

    Prevents two equally-scored subjects from always producing the same
    ordering, which would cause the same suggestion to fire repeatedly.
    """
    return random.uniform(-_JITTER_RANGE, _JITTER_RANGE)
