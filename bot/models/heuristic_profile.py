from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base

# Default weight config seeded during /start onboarding
DEFAULT_HEURISTIC_CONFIG: dict = {
    "recency": "medium",
    "cooldown": "high",
    "strategy_align": "medium",
    "novelty": "medium",
    "platform_fit": "medium",
    "jitter": "low",
}


class HeuristicProfile(Base):
    __tablename__ = "heuristic_profiles"

    profile_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    name: Mapped[str] = mapped_column(default="default")
    # JSON dict mapping heuristic name → weight level ("off"/"low"/"medium"/"high")
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=lambda: dict(DEFAULT_HEURISTIC_CONFIG))
