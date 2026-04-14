"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger, primary_key=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("cooldown_days", sa.Integer, nullable=False, server_default="14"),
    )

    op.create_table(
        "subjects",
        sa.Column("subject_id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "source",
            sa.Enum("manual", "ai_predicted", name="subjectsource"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "pending_approval", "archived", name="subjectstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_posted_at", sa.DateTime, nullable=True),
        sa.Column("embedding_id", sa.String(64), nullable=True),
    )

    op.create_table(
        "posts",
        sa.Column("post_id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("subject_id", sa.Uuid, sa.ForeignKey("subjects.subject_id"), nullable=True),
        sa.Column(
            "platform",
            sa.Enum("instagram", "tiktok", "threads", "other", name="postplatform"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum("manual_confirm", "imported", "skipped", name="postsource"),
            nullable=False,
        ),
        sa.Column("posted_at", sa.DateTime, nullable=False),
        sa.Column("caption_excerpt", sa.Text, nullable=True),
    )

    op.create_table(
        "reminders",
        sa.Column("reminder_id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("schedule_expression", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_fired_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "strategy_notes",
        sa.Column("note_id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding_id", sa.String(64), nullable=True),
    )

    op.create_table(
        "heuristic_profiles",
        sa.Column("profile_id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, server_default="default"),
        sa.Column("config", sa.JSON, nullable=False),
    )

    op.create_table(
        "import_batches",
        sa.Column("batch_id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("imported_at", sa.DateTime, nullable=False),
    )

    # FSM state table (used by bot/db/fsm_storage.py)
    op.create_table(
        "fsm_state",
        sa.Column("user_id", sa.BigInteger, primary_key=True),
        sa.Column("chat_id", sa.BigInteger, primary_key=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("data", sa.Text, nullable=True),  # JSON-encoded dict
    )


def downgrade() -> None:
    op.drop_table("fsm_state")
    op.drop_table("import_batches")
    op.drop_table("heuristic_profiles")
    op.drop_table("strategy_notes")
    op.drop_table("reminders")
    op.drop_table("posts")
    op.drop_table("subjects")
    op.drop_table("users")
