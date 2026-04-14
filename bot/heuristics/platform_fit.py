"""Platform fit heuristic — basic platform preference matching.

In v1, all subjects are considered platform-agnostic. This heuristic
returns a neutral 0.5 score. Extend it when per-subject platform tags
are added in a future iteration.
"""
from bot.heuristics.registry import SuggestionContext
from bot.models import Subject


def platform_fit(subject: Subject, ctx: SuggestionContext) -> float:
    """Return 0.5 (neutral) for all subjects in v1.

    Future: match subject.platform_tags against ctx.platform_hint.
    """
    return 0.5
