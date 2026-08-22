"""Entrega de códigos de verificación por SMTP (Gmail, Outlook u otro proveedor)."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from html import escape

import httpx


def send_verification_email(recipient: str, name: str | None, code: str) -> tuple[bool, str]:
    """Devuelve (entregado, detalle). El código solo aparece en modo de desarrollo."""
    if os.environ.get("DEBUG_VERIFICATION_CODES", "false").lower() == "true":
        return True, code

    sender_name = os.environ.get("SMTP_FROM_NAME", "Nexia AI").strip() or "Nexia AI"
    greeting = (name or "").strip().split(" ")[0] or "Hola"
    html_greeting = escape(greeting)
    subject = f"{code} es tu código de verificación de Nexia"
    plain_body = (
        f"{greeting},\n\nTu código de verificación de Nexia es: {code}\n\n"
        "Caduca en 10 minutos. Si no creaste esta cuenta, ignora este mensaje."
    )
    html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;padding:32px;color:#2c2925">
          <div style="font-size:20px;font-weight:700;color:#c15f3c">Nexia AI</div>
          <h1 style="font-size:26px;margin:28px 0 10px">Verifica tu correo</h1>
          <p>{html_greeting}, usa este código para activar tu cuenta:</p>
          <div style="font-size:36px;letter-spacing:10px;font-weight:700;background:#f4eee6;padding:20px;text-align:center;border-radius:12px">{code}</div>
          <p style="color:#77706a;font-size:13px;margin-top:22px">Caduca en 10 minutos. Si no creaste esta cuenta, ignora este mensaje.</p>
        </div>
    """

    # Render Free bloquea puertos SMTP; una API HTTPS funciona en todos sus planes.
    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    resend_from = os.environ.get("RESEND_FROM_EMAIL", "").strip()
    if resend_key and resend_from:
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                json={
                    "from": f"{sender_name} <{resend_from}>",
                    "to": [recipient],
                    "subject": subject,
                    "text": plain_body,
                    "html": html_body,
                },
                timeout=20.0,
            )
            if response.status_code >= 400:
                return False, f"El servicio de correo rechazó el envío ({response.status_code})."
            return True, "Código enviado"
        except httpx.HTTPError as exc:
            return False, f"No se pudo enviar el correo ({exc.__class__.__name__}). Inténtalo de nuevo."

    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    from_email = os.environ.get("SMTP_FROM_EMAIL", "").strip() or user
    if not host or not user or not password or not from_email:
        return False, "El envío de correo todavía no está configurado. Contacta al administrador."

    port = int(os.environ.get("SMTP_PORT", "587"))
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{from_email}>"
    message["To"] = recipient
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                smtp.login(user, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                if use_tls:
                    smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        return False, f"No se pudo enviar el correo ({exc.__class__.__name__}). Inténtalo de nuevo."
    return True, "Código enviado"
