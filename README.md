# Nexia AI

Plataforma SaaS multiusuario de IA construida con FastAPI. Incluye cuentas verificadas,
planes Free/Premium, chats privados, control de créditos, archivos descargables y acceso
desde Claude Code o ChatGPT Codex mediante un token personal.

## Funciones

- Registro con contraseña y verificación por código de 6 dígitos enviado por SMTP.
- Inicio de sesión opcional con Google OAuth; Google entrega el correo ya verificado.
- Plan Free: Claude Haiku 4.5 y Claude Sonnet 4.6.
- Plan Premium: todos los modelos documentados, con vencimiento configurable por días.
- Selector de modelo en el compositor, tema claro/oscuro y diseño cálido tipo Claude.
- Conversaciones independientes, historial privado y consumo auditable.
- Creación y descarga de ZIP, PDF, XLSX, DOCX y HTML desde el propio chat.
- Token personal rotatorio para endpoints compatibles con Anthropic y OpenAI Responses.
- Panel de configuración con cuenta, plan, facturación, días, créditos e integraciones.
- Panel administrativo para claves del proveedor, créditos, planes y vencimientos.
- API keys cifradas; los tokens personales se guardan únicamente como hash SHA-256.
- SQLite en desarrollo y PostgreSQL en producción.

## Ejecutar localmente

Requiere Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Abre `http://localhost:8000`. Define `ADMIN_EMAIL` y `ADMIN_PASSWORD` antes del
primer arranque. Para probar el registro sin enviar correo, usa
`DEBUG_VERIFICATION_CODES=true`; el código aparecerá solo en la pantalla local.

## Correo de verificación

En **Render Free** usa la API HTTPS de Resend, porque ese plan bloquea las salidas por
los puertos SMTP 25, 465 y 587:

1. Añade y verifica un dominio en Resend.
2. Crea una API key.
3. Define `RESEND_API_KEY` y `RESEND_FROM_EMAIL=acceso@tu-dominio.com` en Render.

Nexia también admite SMTP estándar en desarrollo o en un servicio Render de pago. Con
una cuenta emisora de Gmail:

1. Activa la verificación en dos pasos en la cuenta emisora.
2. Crea una contraseña de aplicación.
3. Configura `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USE_TLS=true`.
4. Coloca el correo en `SMTP_USER` y `SMTP_FROM_EMAIL`, y la contraseña de aplicación
   en `SMTP_PASSWORD`.

Los códigos caducan en 10 minutos, tienen un máximo de 5 intentos y el reenvío tiene
una espera de 60 segundos. Nexia guarda únicamente el hash HMAC del código.

## Google OAuth

En Google Cloud crea un cliente OAuth web y autoriza:

- Local: `http://localhost:8000/auth/google/callback`
- Producción: `https://tu-dominio.com/auth/google/callback`

Define `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` y `APP_BASE_URL` (sin `/` final).

## Planes y saldo

El control se aplica en el servidor y también a las integraciones externas.

- Cada respuesta completada consume 1 crédito en una cuenta activa.
- Si el proveedor falla, Nexia devuelve la reserva.
- Sin clave activa, la cuenta usa la prueba diaria si existe `TRIAL_API_KEY`.
- El plan limita los modelos; los créditos limitan cuántas respuestas puede generar.
- La documentación del proveedor no expone un endpoint de balance, por lo que el saldo
  externo se consulta manualmente en `https://api.mwapi.dev/reseller`.

## Archivos descargables

Si el mensaje pide un ZIP, PDF, Excel, Word o HTML, Nexia indica al modelo que produzca
el contenido completo, lo convierte en el formato real, lo guarda como binario en la
base de datos y muestra un botón de descarga. Al usar PostgreSQL, los archivos sobreviven
a reinicios de Render.

## Claude Code y Codex

Cada cliente genera su token `nxa_...` en **Configuración → Claude Code y Codex**.
El token completo se muestra una sola vez.

- Anthropic compatible: base URL `https://tu-dominio.com/api/anthropic`.
- OpenAI Responses compatible: base URL `https://tu-dominio.com/v1`.

El endpoint Responses traduce mensajes y llamadas de herramientas a
`POST {API_BASE_URL}/chat/completions`. La ejecución de herramientas requiere que el
proveedor subyacente acepte herramientas en su formato compatible con OpenAI.

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `SECRET_KEY` | Firma sesiones, CSRF, OAuth y códigos. Debe ser larga y estable. |
| `API_KEY_ENCRYPTION_KEY` | Cifra claves API; no cambiar tras publicar. |
| `DATABASE_URL` | SQLite o PostgreSQL. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Administrador inicial. |
| `API_BASE_URL` | Por defecto `https://api.mwapi.dev/v1`. |
| `TRIAL_API_KEY` / `DAILY_MESSAGE_LIMIT` | Prueba gratuita opcional. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth web de Google. |
| `APP_BASE_URL` | Origen público del sitio. |
| `COOKIE_SECURE` | `true` en Render/HTTPS. |
| `RESEND_API_KEY` / `RESEND_FROM_EMAIL` | Envío HTTPS recomendado para Render Free. |
| `SMTP_HOST` / `SMTP_PORT` | Servidor SMTP emisor. |
| `SMTP_USER` / `SMTP_PASSWORD` | Credenciales SMTP. |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | Remitente visible. |
| `SMTP_USE_TLS` | Normalmente `true` con el puerto 587. |
| `DEBUG_VERIFICATION_CODES` | Solo local; nunca `true` en producción. |

## Desplegar en Render

1. Sube el proyecto a GitHub.
2. En Render elige **New → Blueprint** y selecciona el repositorio.
3. Render leerá `render.yaml` y creará el servicio web y PostgreSQL.
4. Completa las variables marcadas como secretas, especialmente Resend y `APP_BASE_URL`.
5. Tras conocer la URL pública, añádela al callback OAuth de Google y despliega de nuevo.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las migraciones son aditivas: conservan cuentas y chats existentes; esas cuentas se
marcan como verificadas al incorporar la nueva columna.
