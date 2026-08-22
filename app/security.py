"""Contraseñas, cookies, CSRF, OAuth state y cifrado de claves API."""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import hmac

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")
COOKIE_NAME = "nexia_session"
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", str(60 * 60 * 24 * 7)))

_session_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="nexia-session")
_csrf_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="nexia-csrf")
_oauth_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="nexia-google-oauth")

_fernet_secret = os.environ.get("API_KEY_ENCRYPTION_KEY") or SECRET_KEY
_fernet_key = base64.urlsafe_b64encode(hashlib.sha256(_fernet_secret.encode("utf-8")).digest())
_fernet = Fernet(_fernet_key)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    if not hashed or hashed.startswith("!"):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def make_session(user_id: int) -> str:
    return _session_serializer.dumps({"uid": user_id})


def read_session(token: str | None) -> int | None:
    if not token:
        return None
    try:
        data = _session_serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    return int(uid) if isinstance(uid, int) else None


def make_csrf(user_id: int) -> str:
    return _csrf_serializer.dumps({"uid": user_id, "purpose": "csrf"})


def verify_csrf(token: str | None, user_id: int) -> bool:
    if not token:
        return False
    try:
        data = _csrf_serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return data == {"uid": user_id, "purpose": "csrf"}


def make_oauth_state() -> str:
    return _oauth_serializer.dumps({"nonce": secrets.token_urlsafe(24)})


def verify_oauth_state(state: str | None) -> bool:
    if not state:
        return False
    try:
        data = _oauth_serializer.loads(state, max_age=600)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(data.get("nonce"), str)


def encrypt_api_key(value: str) -> str:
    return _fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Compatibilidad temporal durante la migración de instalaciones antiguas.
        return value if value.startswith("sk-") else ""


def is_encrypted_api_key(value: str) -> bool:
    return value.startswith("gAAAA")


def hash_verification_code(user_id: int, code: str) -> str:
    payload = f"verify:{user_id}:{code}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_verification_code(user_id: int, code: str, expected_hash: str | None) -> bool:
    if not expected_hash:
        return False
    return hmac.compare_digest(hash_verification_code(user_id, code), expected_hash)


def generate_client_token() -> tuple[str, str, str]:
    """Devuelve el token visible una vez, su hash y un prefijo identificable."""
    raw = "nxa_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, digest, raw[:12]


def hash_client_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
