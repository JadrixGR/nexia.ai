"""Consulta segura y normalización del saldo real de una clave MWAPI."""
from __future__ import annotations

from typing import Any

import httpx


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_provider_usage(raw: Any) -> dict[str, Any]:
    """Convierte las variantes de /v1/usage en un contrato estable para la UI."""
    root = _mapping(raw)
    payload = _mapping(root.get("data")) or root
    quota = _mapping(payload.get("quota"))
    usage = _mapping(payload.get("usage"))
    today = _mapping(usage.get("today"))
    total = _mapping(usage.get("total"))
    wallet = _mapping(payload.get("wallet"))

    balance = _first_number(
        payload.get("balance"),
        wallet.get("balance"),
        payload.get("remaining_balance"),
    )
    quota_limit = _first_number(quota.get("limit"), payload.get("quota_limit"))
    quota_used = _first_number(quota.get("used"), payload.get("quota_used"))
    quota_remaining = _first_number(
        quota.get("remaining"),
        payload.get("quota_remaining"),
        quota_limit - quota_used if quota_limit is not None and quota_used is not None else None,
    )
    today_requests = _first_number(
        today.get("requests"),
        today.get("request_count"),
        usage.get("today_requests"),
        payload.get("today_requests"),
    )
    total_requests = _first_number(
        total.get("requests"),
        total.get("request_count"),
        usage.get("total_requests"),
        payload.get("total_requests"),
        payload.get("requests"),
    )

    return {
        "available": True,
        "mode": str(payload.get("mode") or payload.get("billing_mode") or "unknown"),
        "status": str(payload.get("status") or "active"),
        "plan": payload.get("plan_name") or payload.get("plan") or payload.get("subscription"),
        "currency": str(payload.get("currency") or wallet.get("currency") or "USD").upper(),
        "balance": balance,
        "quota": {
            "limit": quota_limit,
            "used": quota_used,
            "remaining": quota_remaining,
        },
        "requests": {
            "today": int(today_requests) if today_requests is not None else None,
            "total": int(total_requests) if total_requests is not None else None,
        },
    }


async def fetch_codex_usage(codex_api_key: str) -> dict:
    """Consulta el saldo de tokens de una clave Codex en nghimmo.com."""
    if not codex_api_key:
        return {"available": False, "reason": "no_codex_api_key"}
    check_url = "https://api.nghimmo.com/check"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            response = await client.get(
                check_url,
                headers={
                    "Authorization": f"Bearer {codex_api_key}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError:
        return {"available": False, "reason": "provider_unreachable"}
    if response.status_code >= 400:
        return {
            "available": False,
            "reason": "provider_rejected",
            "provider_status": response.status_code,
        }
    try:
        raw = response.json()
    except ValueError:
        return {"available": False, "reason": "invalid_provider_response"}

    root = raw if isinstance(raw, dict) else {}
    tokens_remaining = _first_number(
        root.get("tokens_remaining"),
        root.get("remaining_tokens"),
        root.get("remaining"),
        root.get("balance"),
        root.get("quota_remaining"),
    )
    tokens_used = _first_number(
        root.get("tokens_used"),
        root.get("used_tokens"),
        root.get("used"),
    )
    tokens_limit = _first_number(
        root.get("tokens_limit"),
        root.get("limit"),
        root.get("quota_limit"),
    )
    return {
        "available": True,
        "tokens_remaining": int(tokens_remaining) if tokens_remaining is not None else None,
        "tokens_used": int(tokens_used) if tokens_used is not None else None,
        "tokens_limit": int(tokens_limit) if tokens_limit is not None else None,
        "raw": root,
    }


async def fetch_provider_usage(base_url: str, api_key: str) -> dict[str, Any]:
    """Consulta MWAPI sin exponer la clave ni propagar detalles sensibles de errores."""
    if not api_key:
        return {"available": False, "reason": "no_api_key"}
    usage_url = f"{base_url.rstrip('/')}/usage"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            response = await client.get(
                usage_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError:
        return {"available": False, "reason": "provider_unreachable"}
    if response.status_code >= 400:
        return {
            "available": False,
            "reason": "provider_rejected",
            "provider_status": response.status_code,
        }
    try:
        return normalize_provider_usage(response.json())
    except ValueError:
        return {"available": False, "reason": "invalid_provider_response"}
