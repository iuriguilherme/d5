"""Cooldown heuristic — hard excludes subjects posted within cooldown window."""
import math
from datetime import timezone

from bot.heuristics.registry import SuggestionContext
from bot.models import Subject


def cooldown(subject: Subject, ctx: SuggestionContext) -> float:
    """Return -inf if subject was posted within cooldown_days; 0.0 otherwise."""
    if subject.last_posted_at is None:
        return 0.0

    last = subject.last_posted_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    days_since = (ctx.now - last).total_seconds() / 86400
    if days_since < ctx.cooldown_days:
        return -math.inf  # hard exclusion

    return 0.0
