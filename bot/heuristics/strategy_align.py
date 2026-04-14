"""Strategy alignment heuristic — cosine similarity vs strategy notes.

Computed lazily at suggestion time from pre-queried strategy distances.
No Subject.strategy_weight column needed.
"""
from bot.heuristics.registry import SuggestionContext
from bot.models import Subject


def strategy_align(subject: Subject, ctx: SuggestionContext) -> float:
    """Average cosine similarity between subject embedding and strategy notes.

    ctx.strategy_embeddings contains [{id, distance}] where distance is
    cosine distance in [0, 2]. Similarity = 1 - distance/2 → [0, 1].

    Returns 0.0 when no strategy notes exist (neutral, not a penalty).
    """
    if not ctx.strategy_embeddings:
        return 0.0

    similarities = [1.0 - (entry["distance"] / 2.0) for entry in ctx.strategy_embeddings]
    return sum(similarities) / len(similarities)
