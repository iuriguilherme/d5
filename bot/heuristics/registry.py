"""HeuristicRegistry — pluggable heuristic callable registry."""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

WEIGHT_VALUES = {"off": 0.0, "low": 0.5, "medium": 1.0, "high": 2.0}


@dataclass
class SuggestionContext:
    user_id: int
    cooldown_days: int
    now: Any  # datetime
    platform_hint: str | None
    strategy_embeddings: list[dict]  # [{id, distance}] from VectorStore
    profile_config: dict[str, str]  # heuristic name → weight level


HeuristicFn = Callable[["Subject", SuggestionContext], float]  # type: ignore[name-defined]


class HeuristicRegistry:
    def __init__(self) -> None:
        self._heuristics: dict[str, HeuristicFn] = {}
        self._order: list[str] = []

    def register(self, name: str, fn: HeuristicFn) -> None:
        self._heuristics[name] = fn
        if name not in self._order:
            self._order.append(name)

    def get_enabled(self, profile_config: dict[str, str]) -> list[tuple[str, float, HeuristicFn]]:
        """Return [(name, weight, fn)] for heuristics with weight != 'off'."""
        result = []
        for name in self._order:
            fn = self._heuristics.get(name)
            if fn is None:
                continue
            level = profile_config.get(name, "medium")
            weight = WEIGHT_VALUES.get(level, 1.0)
            if weight > 0:
                result.append((name, weight, fn))
        return result
