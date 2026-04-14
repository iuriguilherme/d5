import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class PostPlatform(str, enum.Enum):
    instagram = "instagram"
    tiktok = "tiktok"
    threads = "threads"
    other = "other"


class PostSource(str, enum.Enum):
    manual_confirm = "manual_confirm"
    imported = "imported"
    skipped = "skipped"  # user pressed [Skip] on a reminder suggestion


class Post(Base):
    __tablename__ = "posts"

    post_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    subject_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("subjects.subject_id"), default=None
    )

    platform: Mapped[PostPlatform] = mapped_column(Enum(PostPlatform), nullable=False)
    source: Mapped[PostSource] = mapped_column(Enum(PostSource), nullable=False)

    posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    caption_excerpt: Mapped[str | None] = mapped_column(Text, default=None)
