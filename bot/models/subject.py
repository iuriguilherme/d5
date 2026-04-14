import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class SubjectSource(str, enum.Enum):
    manual = "manual"
    ai_predicted = "ai_predicted"


class SubjectStatus(str, enum.Enum):
    active = "active"
    pending_approval = "pending_approval"
    archived = "archived"


class Subject(Base):
    __tablename__ = "subjects"

    subject_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[SubjectSource] = mapped_column(Enum(SubjectSource), nullable=False)
    status: Mapped[SubjectStatus] = mapped_column(
        Enum(SubjectStatus), nullable=False, default=SubjectStatus.active
    )

    # Set by /posted flow and import backfill; used by recency + cooldown heuristics
    last_posted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # ChromaDB document ID (same UUID as subject_id, stored as string in Chroma)
    embedding_id: Mapped[str | None] = mapped_column(default=None)
    # NOTE: No strategy_weight column — cosine alignment is computed lazily at
    # suggestion time by the strategy_align heuristic via VectorStore.
