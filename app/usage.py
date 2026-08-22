"""Control de prueba gratuita, saldo interno y registro de consumo."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import DailyUsage, Setting, UsageEvent, User
from .security import decrypt_api_key

CHAT_COST = 1


@dataclass
class Access:
    allowed: bool
    reason: str = ""
    api_key: str = ""
    base_url: str = ""
    mode: str = "trial"
    remaining: int = 0
    event_id: int | None = None


def get_settings(db: Session) -> Setting:
    settings = db.get(Setting, 1)
    if settings is None:
        settings = Setting(id=1)
        db.add(settings)
        db.commit()
    return settings


def _today_row(db: Session, user_id: int) -> DailyUsage:
    today = dt.date.today()
    row = (
        db.query(DailyUsage)
        .filter(DailyUsage.user_id == user_id, DailyUsage.usage_date == today)
        .one_or_none()
    )
    if row is None:
        row = DailyUsage(user_id=user_id, usage_date=today, messages_used=0, images_used=0)
        db.add(row)
        db.flush()
    return row


def account_status(db: Session, user: User) -> dict:
    settings = get_settings(db)
    row = _today_row(db, user.id)
    db.commit()
    has_key = bool(user.api_key and decrypt_api_key(user.api_key))
    active = bool(user.is_active and has_key)
    credits_left = max(user.credits - user.credits_used, 0)
    total = max(user.credits, 0)
    used_percent = round(min(user.credits_used / total * 100, 100)) if total else 0
    return {
        "email": user.email,
        "is_admin": user.is_admin,
        "mode": "credits" if active else "trial",
        "credits_left": credits_left,
        "credits": total,
        "credits_used": max(user.credits_used, 0),
        "credit_used_percent": used_percent,
        "is_active": active,
        "has_api_key": has_key,
        "messages_left": max(settings.daily_message_limit - row.messages_used, 0),
        "daily_message_limit": settings.daily_message_limit,
        "messages_today": row.messages_used,
    }


def consume(db: Session, user: User, model: str) -> Access:
    """Reserva un crédito o un uso gratuito antes de contactar al proveedor."""
    settings = get_settings(db)
    row = _today_row(db, user.id)

    # Bloquea la fila en PostgreSQL; SQLite serializa sus escrituras.
    locked_user = db.query(User).filter(User.id == user.id).with_for_update().one()
    api_key = decrypt_api_key(locked_user.api_key)
    active = bool(locked_user.is_active and api_key)
    credits_left = max(locked_user.credits - locked_user.credits_used, 0)

    if active:
        if credits_left < CHAT_COST:
            db.commit()
            return Access(
                allowed=False,
                reason="Tu saldo se agotó. Contacta al administrador para recargar créditos.",
            )
        locked_user.credits_used += CHAT_COST
        row.messages_used += 1
        event = UsageEvent(user_id=user.id, kind="chat", mode="credits", model=model)
        db.add(event)
        db.flush()
        event_id = event.id
        db.commit()
        return Access(
            allowed=True,
            api_key=api_key,
            base_url=settings.api_base_url.rstrip("/"),
            mode="credits",
            remaining=max(locked_user.credits - locked_user.credits_used, 0),
            event_id=event_id,
        )

    if row.messages_used >= settings.daily_message_limit:
        db.commit()
        return Access(
            allowed=False,
            reason=(
                f"Alcanzaste el límite gratuito de hoy ({settings.daily_message_limit} mensajes). "
                "Solicita la activación de tu cuenta para continuar."
            ),
        )

    trial_key = decrypt_api_key(settings.trial_api_key)
    if not trial_key:
        db.commit()
        return Access(
            allowed=False,
            reason="Tu cuenta aún no está activa y la prueba gratuita no está configurada.",
        )

    row.messages_used += 1
    event = UsageEvent(user_id=user.id, kind="chat", mode="trial", model=model)
    db.add(event)
    db.flush()
    event_id = event.id
    db.commit()
    return Access(
        allowed=True,
        api_key=trial_key,
        base_url=settings.api_base_url.rstrip("/"),
        mode="trial",
        remaining=max(settings.daily_message_limit - row.messages_used, 0),
        event_id=event_id,
    )


def refund(db: Session, user: User, access: Access) -> None:
    """Revierte exactamente la reserva asociada a una llamada fallida."""
    row = _today_row(db, user.id)
    row.messages_used = max(row.messages_used - 1, 0)
    if access.mode == "credits":
        user.credits_used = max(user.credits_used - CHAT_COST, 0)
    if access.event_id:
        event = db.get(UsageEvent, access.event_id)
        if event:
            db.delete(event)
    db.commit()
