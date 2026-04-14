from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class Reminder(Base):
    __tablename__ = "reminders"

    reminder_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    schedule_expression: Mapped[str] = mapped_column(String(128), nullable=False)  # cron string
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
