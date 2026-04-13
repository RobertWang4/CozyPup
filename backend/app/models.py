import uuid
import sqlalchemy as sa
from datetime import date, datetime, time

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, JSON, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

# ---------- Enums ----------

import enum


class Species(str, enum.Enum):
    dog = "dog"
    cat = "cat"
    other = "other"




class EventType(str, enum.Enum):
    log = "log"
    appointment = "appointment"
    reminder = "reminder"


class EventCategory(str, enum.Enum):
    daily = "daily"
    diet = "diet"
    medical = "medical"
    abnormal = "abnormal"


class EventSource(str, enum.Enum):
    chat = "chat"
    manual = "manual"


class TaskType(str, enum.Enum):
    routine = "routine"
    special = "special"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class SourceType(str, enum.Enum):
    chat_turn = "chat_turn"
    daily_summary = "daily_summary"
    calendar_event = "calendar_event"
    knowledge_base = "knowledge_base"


# ---------- Models ----------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    auth_provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "apple" | "google" | "email" | "dev"
    password_hash: Mapped[str | None] = mapped_column(String(255))
    phone_number: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    subscription_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="trial")  # "trial" | "active" | "expired"
    trial_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_product_id: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str] = mapped_column(String(500), default="")

    # Family plan
    family_role: Mapped[str | None] = mapped_column(String(20))  # "payer" | "member" | null
    family_payer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))

    pets: Mapped[list["Pet"]] = relationship(back_populates="owner", cascade="all, delete-orphan", foreign_keys="Pet.user_id")
    sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Pet(Base):
    __tablename__ = "pets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    species: Mapped[Species] = mapped_column(Enum(Species), nullable=False)
    species_locked: Mapped[bool] = mapped_column(default=False)
    breed: Mapped[str] = mapped_column(String(100), default="")
    birthday: Mapped[date | None] = mapped_column(Date)
    weight: Mapped[float | None] = mapped_column(Float)
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    color_hex: Mapped[str] = mapped_column(String(6), nullable=False)

    # Flexible profile — AI gradually fills this JSON with any pet info learned from conversation
    profile: Mapped[dict | None] = mapped_column(JSON)
    # Soul.md-style narrative profile maintained by the LLM
    profile_md: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner: Mapped["User"] = relationship(back_populates="pets")
    events: Mapped[list["CalendarEvent"]] = relationship(back_populates="pet", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="pet", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)  # one per calendar day
    context_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # compressed chat history from Context Agent
    summarized_up_to: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)  # last message ID included in summary
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_saved: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    title: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    context_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summarized_up_to: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["Chat"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    cards_json: Mapped[str | None] = mapped_column(Text)  # JSON string of card data, nullable
    image_urls: Mapped[list | None] = mapped_column(JSON)  # saved chat image paths, e.g. ["/api/v1/calendar/photos/xxx.jpg"]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"))
    pet_ids: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # multi-pet: list of UUID strings
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[time | None] = mapped_column(Time)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False, default=EventType.log)
    category: Mapped[EventCategory] = mapped_column(Enum(EventCategory), nullable=False, default=EventCategory.daily)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[EventSource] = mapped_column(Enum(EventSource), nullable=False, default=EventSource.manual)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    photos: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    location_name: Mapped[str | None] = mapped_column(String(300))
    location_address: Mapped[str | None] = mapped_column(String(500))
    location_lat: Mapped[float | None] = mapped_column(Float)
    location_lng: Mapped[float | None] = mapped_column(Float)
    place_id: Mapped[str | None] = mapped_column(String(300))
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)  # spending amount
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # push notification time
    reminder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reminders.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # who recorded this event (for shared pets)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    pet: Mapped["Pet"] = relationship(back_populates="events")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # "medication", "vaccine", "checkup"
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    trigger_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # who created this reminder (for shared pets)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    pet: Mapped["Pet"] = relationship(back_populates="reminders")


class FamilyInvite(Base):
    __tablename__ = "family_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inviter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    invitee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # "pending" | "accepted" | "revoked"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PetCoOwner(Base):
    __tablename__ = "pet_co_owners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("pet_id", "user_id", name="uq_pet_co_owners"),)


class PetShareToken(Base):
    __tablename__ = "pet_share_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyTask(Base):
    __tablename__ = "daily_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[TaskType] = mapped_column(Enum(TaskType), nullable=False, default=TaskType.routine)
    daily_target: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pet: Mapped["Pet"] = relationship()
    completions: Mapped[list["DailyTaskCompletion"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class DailyTaskCompletion(Base):
    __tablename__ = "daily_task_completions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("daily_tasks.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["DailyTask"] = relationship(back_populates="completions")

    __table_args__ = (
        sa.UniqueConstraint("task_id", "date", name="uq_task_completions_task_date"),
    )


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="ios")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    pet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pets.id", ondelete="SET NULL"))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(1536), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    species: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    url: Mapped[str | None] = mapped_column(String(2000))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        sa.UniqueConstraint("user_id", "session_date", name="uq_daily_summaries_user_date"),
    )


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(128))
    args_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
