"""Novelty heuristic — rewards subjects that have never been posted."""
from bot.heuristics.registry import SuggestionContext
from bot.models import Subject


def novelty(subject: Subject, ctx: SuggestionContext) -> float:
    """Return 1.0 for never-posted subjects, 0.0 for subjects posted before."""
    return 1.0 if subject.last_posted_at is None else 0.0
