"""Planes comerciales y acceso a modelos, siempre validados en el servidor."""
from __future__ import annotations

import datetime as dt

from .models import User

MODEL_CATALOG = [
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5", "free"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6", "free"),
    ("claude-sonnet-5", "Claude Sonnet 5", "premium"),
    ("claude-opus-4-6", "Claude Opus 4.6", "premium"),
    ("claude-opus-4-7", "Claude Opus 4.7", "premium"),
    ("claude-opus-4-8", "Claude Opus 4.8", "premium"),
    ("claude-opus-5", "Claude Opus 5", "premium"),
]
MODEL_IDS = {model_id for model_id, _label, _plan in MODEL_CATALOG}
FREE_MODEL_IDS = {model_id for model_id, _label, plan in MODEL_CATALOG if plan == "free"}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def effective_plan(user: User) -> str:
    if user.plan != "premium":
        return "free"
    if user.plan_expires_at and user.plan_expires_at <= utcnow():
        return "free"
    return "premium"


def days_left(user: User) -> int | None:
    if effective_plan(user) != "premium" or not user.plan_expires_at:
        return None
    seconds = max((user.plan_expires_at - utcnow()).total_seconds(), 0)
    return max(1, int((seconds + 86_399) // 86_400)) if seconds else 0


def allowed_model_ids(user: User) -> set[str]:
    return MODEL_IDS if effective_plan(user) == "premium" else FREE_MODEL_IDS


def models_for_user(user: User) -> list[dict]:
    plan = effective_plan(user)
    return [
        {
            "id": model_id,
            "label": label,
            "tier": tier,
            "allowed": tier == "free" or plan == "premium",
        }
        for model_id, label, tier in MODEL_CATALOG
    ]


def choose_allowed_model(user: User, requested: str, default: str = "claude-sonnet-4-6") -> str:
    allowed = allowed_model_ids(user)
    if requested in allowed:
        return requested
    if default in allowed:
        return default
    return "claude-haiku-4-5-20251001"

