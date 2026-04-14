"""SuggestionEngine — scores active subjects through the heuristics pipeline."""
import logging
import math
import random
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.heuristics.cooldown import cooldown
from bot.heuristics.jitter import jitter
from bot.heuristics.novelty import novelty
from bot.heuristics.platform_fit import platform_fit
from bot.heuristics.recency import recency
from bot.heuristics.registry import HeuristicRegistry, SuggestionContext
from bot.heuristics.strategy_align import strategy_align
from bot.models import HeuristicProfile, Subject, User
from bot.models.subject import SubjectStatus
from bot.vector.client import VectorStore

logger = logging.getLogger(__name__)


class NoSubjectAvailableError(Exception):
    """Raised when all active subjects are in cooldown or the pool is empty."""


def build_default_registry() -> HeuristicRegistry:
    registry = HeuristicRegistry()
    registry.register("recency", recency)
    registry.register("cooldown", cooldown)
    registry.register("strategy_align", strategy_align)
    registry.register("novelty", novelty)
    registry.register("platform_fit", platform_fit)
    registry.register("jitter", jitter)
    return registry


class SuggestionEngine:
    EPSILON = 0.10  # 10% chance to pick randomly from top-3

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        vector_store: VectorStore,
        registry: HeuristicRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._vector_store = vector_store
        self._registry = registry or build_default_registry()

    async def suggest(
        self,
        user_id: int,
        platform_hint: str | None = None,
        exclude_ids: list[UUID] | None = None,
    ) -> Subject:
        """Score all active subjects and return the best candidate.

        Args:
            user_id: Telegram user ID.
            platform_hint: Reminder platform (used by platform_fit heuristic).
            exclude_ids: Subject IDs to exclude from this session (used by
                         [Suggest another] button to avoid re-suggesting).

        Raises:
            NoSubjectAvailableError: if pool is empty or all subjects in cooldown.
        """
        now = datetime.now(timezone.utc)
        exclude = set(exclude_ids or [])

        async with self._session_factory() as session:
            # Load active subjects
            stmt = select(Subject).where(
                Subject.user_id == user_id,
                Subject.status == SubjectStatus.active,
            )
            subjects = (await session.execute(stmt)).scalars().all()
            subjects = [s for s in subjects if s.subject_id not in exclude]

            if not subjects:
                raise NoSubjectAvailableError("Subject pool is empty.")

            # Load heuristic profile
            profile_stmt = select(HeuristicProfile).where(
                HeuristicProfile.user_id == user_id
            )
            profile = (await session.execute(profile_stmt)).scalars().first()
            profile_config = profile.config if profile else {}

            # Load user cooldown preference
            user = await session.get(User, user_id)
            cooldown_days = user.cooldown_days if user else self._settings.cooldown_days

        # Load strategy embeddings for strategy_align heuristic
        # Use a dummy embedding (zeros) to query all strategy vectors
        strategy_embs = await self._vector_store.query_strategy_alignment(
            user_id, [0.0] * 384, n_results=50
        )

        ctx = SuggestionContext(
            user_id=user_id,
            cooldown_days=cooldown_days,
            now=now,
            platform_hint=platform_hint,
            strategy_embeddings=strategy_embs,
            profile_config=profile_config,
        )

        enabled = self._registry.get_enabled(profile_config)

        # Score subjects
        scored: list[tuple[float, Subject]] = []
        for subject in subjects:
            total = 0.0
            for _name, weight, fn in enabled:
                score = fn(subject, ctx)
                if score == -math.inf:
                    total = -math.inf
                    break
                total += weight * score
            scored.append((total, subject))

        # Filter hard-excluded subjects (cooldown)
        eligible = [(s, sub) for s, sub in scored if s != -math.inf]
        if not eligible:
            raise NoSubjectAvailableError(
                "All subjects are in cooldown — add new ideas with /idea or reduce cooldown in /settings"
            )

        eligible.sort(key=lambda x: x[0], reverse=True)

        # Epsilon-greedy: 10% chance to pick randomly from top-3
        if random.random() < self.EPSILON and len(eligible) >= 2:
            pick_pool = eligible[: min(3, len(eligible))]
            _, selected = random.choice(pick_pool)
        else:
            _, selected = eligible[0]

        logger.info(
            "suggestion_made",
            user_id=user_id,
            subject_id=str(selected.subject_id),
            platform=platform_hint,
        )
        return selected
