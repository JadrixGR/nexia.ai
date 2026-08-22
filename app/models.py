"""Modelos y migraciones aditivas para SQLite o PostgreSQL."""
from __future__ import annotations

import datetime as dt
import os

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./nexia.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    auth_provider: Mapped[str] = mapped_column(String(20), default="local")
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    # La API key se guarda cifrada. credits es lo asignado y credits_used lo consumido.
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    credits: Mapped[int] = mapped_column(Integer, default=0)
    credits_used: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    verification_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    plan_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    client_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_token_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    client_token_created_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120), default="Nueva conversación")
    model: Mapped[str] = mapped_column(String(80), default="claude-sonnet-4-6")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class DailyUsage(Base):
    __tablename__ = "daily_usage"
    __table_args__ = (UniqueConstraint("user_id", "usage_date", name="uq_usage_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    usage_date: Mapped[dt.date] = mapped_column(Date, index=True)
    messages_used: Mapped[int] = mapped_column(Integer, default=0)
    # Se conserva por compatibilidad con instalaciones anteriores.
    images_used: Mapped[int] = mapped_column(Integer, default=0)


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    filename: Mapped[str] = mapped_column(String(180))
    mime_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    trial_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    daily_message_limit: Mapped[int] = mapped_column(Integer, default=3)
    # Campos heredados; el proveedor documentado no anuncia generación de imágenes.
    daily_image_limit: Mapped[int] = mapped_column(Integer, default=0)
    default_model: Mapped[str] = mapped_column(String(80), default="claude-sonnet-4-6")
    api_base_url: Mapped[str] = mapped_column(String(200), default="https://api.mwapi.dev/v1")
    image_model: Mapped[str] = mapped_column(String(80), default="")


def _add_missing_columns() -> None:
    """Migra instalaciones anteriores sin destruir datos existentes."""
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        user_additions = {
            "name": "VARCHAR(100)",
            "auth_provider": "VARCHAR(20) DEFAULT 'local' NOT NULL",
            "google_sub": "VARCHAR(255)",
            "avatar_url": "TEXT",
            # Las cuentas creadas antes de esta función ya usaban correo o Google.
            "email_verified": "BOOLEAN DEFAULT TRUE NOT NULL",
            "verification_code_hash": "VARCHAR(64)",
            "verification_expires_at": "TIMESTAMP",
            "verification_sent_at": "TIMESTAMP",
            "verification_attempts": "INTEGER DEFAULT 0 NOT NULL",
            "plan": "VARCHAR(20) DEFAULT 'free' NOT NULL",
            "plan_started_at": "TIMESTAMP",
            "plan_expires_at": "TIMESTAMP",
            "client_token_hash": "VARCHAR(64)",
            "client_token_prefix": "VARCHAR(20)",
            "client_token_created_at": "TIMESTAMP",
        }
        with engine.begin() as connection:
            for name, sql_type in user_additions.items():
                if name not in user_columns:
                    connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))

    inspector = inspect(engine)
    if "messages" in inspector.get_table_names():
        message_columns = {column["name"] for column in inspector.get_columns("messages")}
        if "conversation_id" not in message_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE messages ADD COLUMN conversation_id INTEGER"))
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages (conversation_id)")
                )
        if "artifact_id" not in message_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE messages ADD COLUMN artifact_id INTEGER"))


def _adopt_legacy_messages() -> None:
    """Agrupa el historial antiguo de cada cliente en una conversación."""
    with SessionLocal() as db:
        user_ids = [
            value
            for (value,) in db.query(Message.user_id)
            .filter(Message.conversation_id.is_(None))
            .distinct()
            .all()
        ]
        for user_id in user_ids:
            conversation = Conversation(
                user_id=user_id,
                title="Conversación anterior",
                model="claude-sonnet-4-6",
            )
            db.add(conversation)
            db.flush()
            db.query(Message).filter(
                Message.user_id == user_id, Message.conversation_id.is_(None)
            ).update({Message.conversation_id: conversation.id}, synchronize_session=False)
        if user_ids:
            db.commit()


def init_db() -> None:
    """Crea tablas, aplica migraciones seguras y prepara la configuración inicial."""
    Base.metadata.create_all(engine)
    _add_missing_columns()
    _adopt_legacy_messages()

    from .security import encrypt_api_key, hash_password, is_encrypted_api_key

    with SessionLocal() as db:
        settings = db.get(Setting, 1)
        if settings is None:
            trial_key = os.environ.get("TRIAL_API_KEY") or None
            db.add(
                Setting(
                    id=1,
                    trial_api_key=encrypt_api_key(trial_key) if trial_key else None,
                    daily_message_limit=int(os.environ.get("DAILY_MESSAGE_LIMIT", "3")),
                    daily_image_limit=0,
                    api_base_url=os.environ.get("API_BASE_URL", "https://api.mwapi.dev/v1"),
                    default_model="claude-sonnet-4-6",
                )
            )
            db.commit()
        elif settings.trial_api_key and not is_encrypted_api_key(settings.trial_api_key):
            settings.trial_api_key = encrypt_api_key(settings.trial_api_key)
            db.commit()

        # Cifra claves en texto plano de versiones anteriores.
        for user in db.query(User).filter(User.api_key.is_not(None)).all():
            if user.api_key and not is_encrypted_api_key(user.api_key):
                user.api_key = encrypt_api_key(user.api_key)
        db.commit()

        admin_email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
        admin_password = os.environ.get("ADMIN_PASSWORD") or ""
        if admin_email and admin_password:
            user = db.query(User).filter(User.email == admin_email).one_or_none()
            if user is None:
                db.add(
                    User(
                        email=admin_email,
                        password_hash=hash_password(admin_password),
                        auth_provider="local",
                        is_admin=True,
                        is_active=False,
                        email_verified=True,
                    )
                )
            else:
                user.is_admin = True
                user.email_verified = True
            db.commit()
