from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class User(Base):
    __tablename__ = "users"

    # Telegram user_id is the natural PK for a single-user bot
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(default=None)
    first_name: Mapped[str | None] = mapped_column(default=None)

    # Configurable per user via /settings; default comes from Settings.cooldown_days
    cooldown_days: Mapped[int] = mapped_column(default=14)
