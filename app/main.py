"""Nexia: chat multiusuario con autenticación, saldo y consumo auditable."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from .models import (
    Conversation,
    Message,
    SessionLocal,
    UsageEvent,
    User,
    init_db,
)
from .security import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    encrypt_api_key,
    hash_password,
    make_csrf,
    make_oauth_state,
    make_session,
    read_session,
    verify_csrf,
    verify_oauth_state,
    verify_password,
)
from .usage import account_status, consume, get_settings, refund

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# IDs copiados de la documentación entregada por el usuario.
CHAT_MODELS = [
    ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
    ("claude-sonnet-5", "Claude Sonnet 5"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ("claude-opus-4-6", "Claude Opus 4.6"),
    ("claude-opus-4-7", "Claude Opus 4.7"),
    ("claude-opus-4-8", "Claude Opus 4.8"),
    ("claude-opus-5", "Claude Opus 5"),
]
MODEL_IDS = {model_id for model_id, _label in CHAT_MODELS}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")

app = FastAPI(title="Nexia", version="2.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = read_session(request.cookies.get(COOKIE_NAME))
    return db.get(User, uid) if uid else None


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = require_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Solo administradores.")
    return user


def require_csrf(request: Request, user: User, form_token: str | None = None) -> None:
    token = form_token or request.headers.get("X-CSRF-Token")
    if not verify_csrf(token, user.id):
        raise HTTPException(status_code=403, detail="La sesión del formulario expiró. Recarga la página.")


def template_context(request: Request, user: User | None = None, **extra) -> dict:
    context = {
        "request": request,
        "user": user,
        "google_enabled": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
    }
    if user:
        context["csrf_token"] = make_csrf(user.id)
    context.update(extra)
    return context


def _set_session_cookie(response: RedirectResponse, request: Request, user_id: int) -> None:
    secure = request.url.scheme == "https" or os.environ.get("COOKIE_SECURE", "").lower() == "true"
    response.set_cookie(
        COOKIE_NAME,
        make_session(user_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _google_redirect_uri(request: Request) -> str:
    if APP_BASE_URL:
        return f"{APP_BASE_URL}/auth/google/callback"
    return str(request.url_for("google_callback"))


def _first_user_can_be_admin(db: Session) -> bool:
    enabled = os.environ.get("FIRST_USER_IS_ADMIN", "false").lower() == "true"
    return enabled and db.query(User).count() == 0


# -------------------------------------------------------------------- páginas


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "index.html", template_context(request, current_user(request, db))
    )


@app.get("/auth", response_class=HTMLResponse)
def auth_page(
    request: Request,
    mode: str = "login",
    error: str | None = None,
    success: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "auth.html",
        template_context(
            request,
            mode="signup" if mode == "signup" else "login",
            error=error,
            success=success,
        ),
    )


@app.post("/auth/register")
def register(
    request: Request,
    name: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    name = " ".join(name.strip().split())[:100]
    if not EMAIL_RE.match(email):
        return RedirectResponse("/auth?mode=signup&error=Ingresa+un+correo+válido", 303)
    if len(password) < 8:
        return RedirectResponse(
            "/auth?mode=signup&error=La+contraseña+debe+tener+al+menos+8+caracteres", 303
        )
    if db.query(User).filter(User.email == email).one_or_none():
        return RedirectResponse("/auth?error=Ese+correo+ya+está+registrado", 303)

    user = User(
        name=name or None,
        email=email,
        password_hash=hash_password(password),
        auth_provider="local",
        is_admin=_first_user_can_be_admin(db),
    )
    db.add(user)
    db.commit()
    response = RedirectResponse("/chat?new=1", 303)
    _set_session_cookie(response, request, user.id)
    return response


@app.post("/auth/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.strip().lower()).one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return RedirectResponse("/auth?error=Correo+o+contraseña+incorrectos", 303)
    response = RedirectResponse("/chat", 303)
    _set_session_cookie(response, request, user.id)
    return response


@app.get("/auth/google")
def google_login(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return RedirectResponse(
            "/auth?error=El+acceso+con+Google+aún+no+está+configurado", 303
        )
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": _google_redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": make_oauth_state(),
        "prompt": "select_account",
    }
    return RedirectResponse(
        "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), 302
    )


@app.get("/auth/google/callback", name="google_callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        return RedirectResponse("/auth?error=Google+canceló+el+inicio+de+sesión", 303)
    if not code or not verify_oauth_state(state):
        return RedirectResponse("/auth?error=La+sesión+de+Google+expiró.+Intenta+de+nuevo", 303)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": _google_redirect_uri(request),
                    "grant_type": "authorization_code",
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]
            profile_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            profile_response.raise_for_status()
            profile = profile_response.json()
    except (httpx.HTTPError, KeyError, ValueError):
        return RedirectResponse(
            "/auth?error=No+se+pudo+validar+tu+cuenta+de+Google", 303
        )

    email = str(profile.get("email") or "").strip().lower()
    google_sub = str(profile.get("sub") or "").strip()
    if not email or not google_sub or not profile.get("email_verified"):
        return RedirectResponse("/auth?error=Google+no+devolvió+un+correo+verificado", 303)

    user = db.query(User).filter(User.google_sub == google_sub).one_or_none()
    if user is None:
        user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(
            name=str(profile.get("name") or "")[:100] or None,
            email=email,
            password_hash="!google-only",
            auth_provider="google",
            google_sub=google_sub,
            avatar_url=str(profile.get("picture") or "") or None,
            is_admin=_first_user_can_be_admin(db),
        )
        db.add(user)
    else:
        user.google_sub = google_sub
        user.auth_provider = "google" if user.password_hash.startswith("!") else "local+google"
        user.name = user.name or str(profile.get("name") or "")[:100] or None
        user.avatar_url = str(profile.get("picture") or "") or user.avatar_url
    db.commit()

    response = RedirectResponse("/chat", 303)
    _set_session_cookie(response, request, user.id)
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", 303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.get("/chat", response_class=HTMLResponse)
def chat_page(
    request: Request,
    conversation: int | None = Query(None),
    new: bool = Query(False),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/auth", 303)

    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .all()
    )
    selected = None
    if not new and conversation is not None:
        selected = next((item for item in conversations if item.id == conversation), None)
    elif not new and conversations:
        selected = conversations[0]

    history = []
    if selected:
        history = (
            db.query(Message)
            .filter(
                Message.user_id == user.id,
                Message.conversation_id == selected.id,
            )
            .order_by(Message.id)
            .all()
        )

    return templates.TemplateResponse(
        request,
        "chat.html",
        template_context(
            request,
            user,
            status=account_status(db, user),
            models=CHAT_MODELS,
            conversations=conversations,
            selected=selected,
            history=history,
        ),
    )


@app.get("/cuenta", response_class=HTMLResponse)
def account_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/auth", 303)
    events = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == user.id)
        .order_by(UsageEvent.id.desc())
        .limit(30)
        .all()
    )
    conversation_count = (
        db.query(Conversation).filter(Conversation.user_id == user.id).count()
    )
    return templates.TemplateResponse(
        request,
        "account.html",
        template_context(
            request,
            user,
            status=account_status(db, user),
            events=events,
            conversation_count=conversation_count,
        ),
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    error: str | None = None,
    success: str | None = None,
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/auth", 303)
    if not user.is_admin:
        return RedirectResponse("/chat", 303)
    clients = db.query(User).order_by(User.created_at.desc()).all()
    rows = [{"user": client, "status": account_status(db, client)} for client in clients]
    return templates.TemplateResponse(
        request,
        "admin.html",
        template_context(
            request,
            user,
            rows=rows,
            settings=get_settings(db),
            models=CHAT_MODELS,
            error=error,
            success=success,
        ),
    )


# ------------------------------------------------------------ admin acciones


@app.post("/admin/settings")
def admin_settings(
    request: Request,
    csrf_token: str = Form(...),
    trial_api_key: str = Form(""),
    daily_message_limit: int = Form(...),
    api_base_url: str = Form(...),
    default_model: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_admin(request, db)
    require_csrf(request, admin, csrf_token)
    settings = get_settings(db)
    if trial_api_key.strip():
        if not trial_api_key.strip().startswith("sk-"):
            return RedirectResponse("/admin?error=La+clave+de+prueba+debe+comenzar+con+sk-", 303)
        settings.trial_api_key = encrypt_api_key(trial_api_key.strip())
    settings.daily_message_limit = max(daily_message_limit, 0)
    settings.api_base_url = api_base_url.strip().rstrip("/") or "https://api.mwapi.dev/v1"
    settings.default_model = (
        default_model if default_model in MODEL_IDS else "claude-sonnet-4-6"
    )
    db.commit()
    return RedirectResponse("/admin?success=Configuración+guardada", 303)


@app.post("/admin/client/{user_id}")
def admin_client(
    user_id: int,
    request: Request,
    csrf_token: str = Form(...),
    api_key: str = Form(""),
    add_credits: int = Form(0),
    notes: str = Form(""),
    action: str = Form(""),
    db: Session = Depends(get_db),
):
    admin = require_admin(request, db)
    require_csrf(request, admin, csrf_token)
    client = db.get(User, user_id)
    if client is None:
        raise HTTPException(404, "Cliente no encontrado")

    if action == "remove_key":
        client.api_key = None
        client.is_active = False
    elif action == "toggle_active":
        if not client.api_key:
            return RedirectResponse("/admin?error=Primero+asigna+una+clave+API+al+cliente", 303)
        client.is_active = not client.is_active
    elif action == "toggle_admin":
        if client.id == admin.id:
            return RedirectResponse("/admin?error=No+puedes+quitarte+tu+propio+acceso+admin", 303)
        client.is_admin = not client.is_admin
    elif action == "delete":
        if client.id == admin.id:
            return RedirectResponse("/admin?error=No+puedes+eliminar+tu+propia+cuenta", 303)
        db.query(Message).filter(Message.user_id == client.id).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.user_id == client.id).delete(
            synchronize_session=False
        )
        db.delete(client)
        db.commit()
        return RedirectResponse("/admin?success=Cliente+eliminado", 303)
    else:
        clean_key = api_key.strip()
        if clean_key:
            if not clean_key.startswith("sk-"):
                return RedirectResponse("/admin?error=La+clave+API+debe+comenzar+con+sk-", 303)
            client.api_key = encrypt_api_key(clean_key)
            client.is_active = True
        if add_credits > 0:
            client.credits += add_credits
        client.notes = notes.strip()[:500] or client.notes
    db.commit()
    return RedirectResponse("/admin?success=Cliente+actualizado", 303)


# ------------------------------------------------------------------- API app


@app.get("/api/status")
def api_status(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return account_status(db, user)


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    require_csrf(request, user)
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .one_or_none()
    )
    if conversation is None:
        raise HTTPException(404, "Conversación no encontrada")
    db.query(Message).filter(Message.conversation_id == conversation.id).delete(
        synchronize_session=False
    )
    db.delete(conversation)
    db.commit()
    return {"ok": True}


@app.post("/api/chat")
async def api_chat(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_csrf(request, user)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Solicitud inválida."}, 400)

    prompt = str(body.get("message") or "").strip()
    if not prompt:
        return JSONResponse({"error": "Escribe un mensaje para continuar."}, 400)
    if len(prompt) > 20_000:
        return JSONResponse({"error": "El mensaje supera el máximo de 20.000 caracteres."}, 400)

    model = str(body.get("model") or "")
    if model not in MODEL_IDS:
        model = get_settings(db).default_model
    if model not in MODEL_IDS:
        model = "claude-sonnet-4-6"

    conversation = None
    raw_conversation_id = body.get("conversation_id")
    if raw_conversation_id is not None:
        try:
            conversation_id = int(raw_conversation_id)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Conversación inválida."}, 400)
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
            .one_or_none()
        )
        if conversation is None:
            return JSONResponse({"error": "La conversación ya no existe."}, 404)

    access = consume(db, user, model)
    if not access.allowed:
        return JSONResponse({"error": access.reason}, 402)

    is_new = conversation is None
    if conversation is None:
        title = " ".join(prompt.split())[:58] or "Nueva conversación"
        conversation = Conversation(user_id=user.id, title=title, model=model)
        db.add(conversation)
        db.flush()
    else:
        conversation.model = model
        conversation.updated_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)

    previous = (
        db.query(Message)
        .filter(
            Message.user_id == user.id,
            Message.conversation_id == conversation.id,
            Message.role.in_(("user", "assistant")),
        )
        .order_by(Message.id.desc())
        .limit(29)
        .all()
    )
    provider_messages = [
        {"role": item.role, "content": item.content}
        for item in reversed(previous)
        if item.content
    ]
    provider_messages.append({"role": "user", "content": prompt})

    db.add(
        Message(
            user_id=user.id,
            conversation_id=conversation.id,
            role="user",
            content=prompt,
        )
    )
    db.commit()
    conversation_id = conversation.id
    conversation_title = conversation.title

    async def stream():
        collected: list[str] = []
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=30.0)
            ) as client:
                async with client.stream(
                    "POST",
                    f"{access.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {access.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                    json={
                        "model": model,
                        "messages": provider_messages,
                        "stream": True,
                    },
                ) as upstream:
                    if upstream.status_code >= 400:
                        detail = (await upstream.aread()).decode("utf-8", "ignore")[:300]
                        refund(db, user, access)
                        yield _sse_error(
                            f"El proveedor respondió {upstream.status_code}: {detail}"
                        )
                        return
                    async for line in upstream.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(payload)
                            delta = chunk["choices"][0]["delta"].get("content")
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        if delta:
                            collected.append(str(delta))
                            yield f"data: {json.dumps({'delta': str(delta)})}\n\n"
        except httpx.HTTPError as exc:
            refund(db, user, access)
            yield _sse_error(f"No se pudo contactar con el proveedor: {exc}")
            return

        answer = "".join(collected).strip()
        if not answer:
            refund(db, user, access)
            yield _sse_error("El proveedor no devolvió contenido.")
            return

        db.add(
            Message(
                user_id=user.id,
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
            )
        )
        saved_conversation = db.get(Conversation, conversation_id)
        if saved_conversation:
            saved_conversation.updated_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
        db.commit()
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": str(conversation_id),
            "X-Conversation-Title": conversation_title.encode("ascii", "ignore").decode(),
            "X-New-Conversation": "1" if is_new else "0",
            "X-Usage-Mode": access.mode,
        },
    )


def _sse_error(message: str) -> str:
    return f"data: {json.dumps({'error': message})}\n\n"


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "app": "nexia",
        "version": os.environ.get("APP_VERSION", "2.0.0"),
    }
