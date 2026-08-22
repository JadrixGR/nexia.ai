"""Pruebas de los flujos críticos sin contactar al proveedor real."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///./tmp/nexia-tests.db"
os.environ["SECRET_KEY"] = "test-session-secret-with-enough-entropy"
os.environ["API_KEY_ENCRYPTION_KEY"] = "test-api-encryption-key"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "admin-password-123"
os.environ["FIRST_USER_IS_ADMIN"] = "false"
os.environ.pop("TRIAL_API_KEY", None)
os.environ.pop("GOOGLE_CLIENT_ID", None)
os.environ.pop("GOOGLE_CLIENT_SECRET", None)

from fastapi.testclient import TestClient

from app.main import app
from app.models import Base, Conversation, Message, SessionLocal, User, engine, init_db
from app.security import encrypt_api_key, make_csrf


class FakeStreamResponse:
    status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    async def aiter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"Respuesta "}}]}'
        yield 'data: {"choices":[{"delta":{"content":"de prueba"}}]}'
        yield "data: [DONE]"


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    def stream(self, *args, **kwargs):
        return FakeStreamResponse()


class NexiaFlowTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        init_db()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def register_client(self, email: str = "cliente@example.com"):
        response = self.client.post(
            "/auth/register",
            data={"name": "Cliente Demo", "email": email, "password": "password-123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        with SessionLocal() as db:
            return db.query(User).filter(User.email == email).one().id

    def test_registration_session_and_account_page(self):
        self.register_client()
        chat = self.client.get("/chat?new=1")
        account = self.client.get("/cuenta")
        self.assertEqual(chat.status_code, 200)
        self.assertIn("Nueva conversación", chat.text)
        self.assertIn("Consumo y créditos", account.text)
        self.assertIn("cliente@example.com", account.text)

    def test_google_button_is_configuration_aware(self):
        page = self.client.get("/auth")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("Continuar con Google", page.text)
        self.assertIn("El acceso con Google aparecerá", page.text)

    def test_chat_stream_creates_conversation_and_consumes_credit(self):
        user_id = self.register_client()
        with SessionLocal() as db:
            user = db.get(User, user_id)
            user.api_key = encrypt_api_key("sk-test-client-key")
            user.is_active = True
            user.credits = 3
            db.commit()
        csrf = make_csrf(user_id)

        with patch("app.main.httpx.AsyncClient", FakeAsyncClient):
            response = self.client.post(
                "/api/chat",
                json={
                    "message": "Diseña una estrategia de lanzamiento",
                    "model": "claude-sonnet-4-6",
                },
                headers={"X-CSRF-Token": csrf},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Respuesta", response.text)
        conversation_id = int(response.headers["X-Conversation-Id"])
        with SessionLocal() as db:
            user = db.get(User, user_id)
            conversation = db.get(Conversation, conversation_id)
            messages = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.id)
                .all()
            )
            self.assertEqual(user.credits_used, 1)
            self.assertEqual(conversation.user_id, user_id)
            self.assertEqual([item.role for item in messages], ["user", "assistant"])
            self.assertEqual(messages[-1].content, "Respuesta de prueba")

    def test_conversations_are_isolated_and_csrf_is_required(self):
        first_user_id = self.register_client("uno@example.com")
        with SessionLocal() as db:
            conversation = Conversation(
                user_id=first_user_id,
                title="Secreto del cliente uno",
                model="claude-sonnet-4-6",
            )
            db.add(conversation)
            db.commit()
            conversation_id = conversation.id

        other_client = TestClient(app)
        response = other_client.post(
            "/auth/register",
            data={"name": "Dos", "email": "dos@example.com", "password": "password-456"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        page = other_client.get(f"/chat?conversation={conversation_id}")
        self.assertNotIn("Secreto del cliente uno", page.text)
        forbidden = other_client.delete(
            f"/api/conversations/{conversation_id}",
            headers={"X-CSRF-Token": "invalid"},
        )
        self.assertEqual(forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()
