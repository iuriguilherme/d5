"""Recency heuristic — penalizes recently posted subjects."""
import math
from datetime import datetime, timezone

from bot.heuristics.registry import SuggestionContext
from bot.models import Subject


def recency(subject: Subject, ctx: SuggestionContext) -> float:
    """Return a score in [0, 1] based on how long ago the subject was last posted.

    Never-posted subjects get a small bonus (0.2).
    Score rises toward 1.0 as time since last post grows.
    """
    if subject.last_posted_at is None:
        return 0.2  # slight novelty bonus for never-posted

    last = subject.last_posted_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    days_since = (ctx.now - last).total_seconds() / 86400
    # Sigmoid-like: score = 1 - exp(-days/cooldown)
    return 1.0 - math.exp(-days_since / max(ctx.cooldown_days, 1))
