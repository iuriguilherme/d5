from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class StrategyNote(Base):
    __tablename__ = "strategy_notes"

    note_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    # ChromaDB document ID in strategy_embeddings_{user_id} collection
    embedding_id: Mapped[str | None] = mapped_column(default=None)
