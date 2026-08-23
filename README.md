# Nexia AI

Plataforma SaaS multiusuario de IA construida con FastAPI. Incluye cuentas verificadas,
planes Free/Premium, chats privados, saldo real de API, archivos descargables, conexión
directa de la API personal con Claude Code y acceso a ChatGPT Codex mediante Nexia.

## Funciones

- Registro con contraseña y verificación por código de 6 dígitos enviado por SMTP.
- Inicio de sesión opcional con Google OAuth; Google entrega el correo ya verificado.
- Plan Free: Claude Haiku 4.5 y Claude Sonnet 4.6.
- Plan Premium: todos los modelos documentados, con vencimiento configurable por días.
- Selector de modelo en el compositor, tema claro/oscuro y diseño cálido tipo Claude.
- Conversaciones independientes, historial privado y consumo auditable.
- Adjuntos privados de hasta 15 MB: PDF, DOCX, XLSX, CSV, texto, código e imágenes.
- Análisis de documentos e imágenes mediante entradas multimodales del proveedor.
- Estado temporal «Pensando…» con actividad de Analista, Creador y Revisor.
- Ilustraciones vectoriales SVG creadas por Claude, sin una API de imágenes adicional.
- Creación y descarga de ZIP, PDF, XLSX, DOCX y HTML desde el propio chat.
- Entrega autenticada de la API personal `sk-...` para conexión directa con Claude Code.
- Token Nexia rotatorio para la integración compatible con OpenAI Responses de Codex.
- Panel de configuración con cuenta, plan, facturación, días, saldo real e integraciones.
- Panel administrativo para claves del proveedor, planes y vencimientos.
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

## Planes y saldo real

El control se aplica en el servidor y también a las integraciones externas.

- Una cuenta activa utiliza directamente la clave API personal que le asigna el administrador.
- El saldo disponible se consulta en `GET {API_BASE_URL}/usage` y se actualiza después de cada respuesta.
- Sin clave activa, la cuenta usa la prueba diaria si existe `TRIAL_API_KEY`.
- El plan limita los modelos y el proveedor controla el saldo real de la clave.

## Archivos descargables

Si el mensaje pide un ZIP, PDF, Excel, Word o HTML, Nexia indica al modelo que produzca
el contenido completo, lo convierte en el formato real, lo guarda como binario en la
base de datos y muestra un botón de descarga. Al usar PostgreSQL, los archivos sobreviven
a reinicios de Render.

El código y el contenido extenso usados para construir un archivo no saturan la respuesta.
Mientras trabaja, Nexia muestra **Pensando…** y la actividad resumida de Analista, Creador
y Revisor; al terminar desaparece y queda solamente la entrega final.

## Adjuntos e imágenes

Cada cliente puede adjuntar hasta 8 archivos por mensaje. Nexia extrae localmente el texto
de PDF, Word, Excel, CSV y archivos de texto/código; las imágenes se envían como entrada
multimodal al proveedor de chat. Los adjuntos se almacenan ligados al propietario y a su chat.

Claude puede analizar las imágenes adjuntas, pero su API no produce imágenes raster PNG/JPG.
Cuando el usuario pide una imagen, Nexia solicita al modelo una ilustración SVG segura,
la muestra dentro del chat y la entrega como archivo descargable. Es apropiada para logos,
iconos y diagramas; no sustituye a un generador de fotografías.

## Claude Code y Codex

El administrador asigna una API personal `sk-...` a cada cliente. En
**Configuración → Claude Code y Codex**, el dueño autenticado puede mostrarla o copiarla
de forma explícita. La clave sigue cifrada en la base de datos, no se incluye en el HTML
inicial y la respuesta que la revela usa `Cache-Control: no-store` y protección CSRF.

- Claude Code se conecta directamente a MWAPI con la API `sk-...` del cliente.
- Codex continúa usando el token Nexia `nxa_...` y la API Responses de Nexia.

Para Claude Code en PowerShell:

```powershell
irm https://claude.ai/install.ps1 | iex
$claudeDir = "$env:USERPROFILE\.local\bin"
$env:Path = "$env:Path;$claudeDir"
$env:ANTHROPIC_BASE_URL="https://api.mwapi.dev/v1"
$env:ANTHROPIC_AUTH_TOKEN="sk-TU_API_PERSONAL"
$headers = @{ Authorization = "Bearer $env:ANTHROPIC_AUTH_TOKEN" }
Invoke-RestMethod "https://api.mwapi.dev/v1/models" -Headers $headers
claude --model claude-sonnet-4-6
```

Si PowerShell indica que `claude` no se reconoce, comprueba
`Test-Path "$env:USERPROFILE\.local\bin\claude.exe"`, añade esa carpeta al `PATH`
del usuario o instala la alternativa oficial con `winget install Anthropic.ClaudeCode`.

Las instrucciones usan el `API_BASE_URL` configurado por el administrador. Según la guía
de MWAPI, Claude Code espera directamente `ANTHROPIC_AUTH_TOKEN=sk-...` y
`ANTHROPIC_BASE_URL=https://api.mwapi.dev/v1`. El saldo mostrado en Nexia corresponde a
esa misma clave. Como la terminal se conecta directamente al proveedor, los límites de
modelos aplicados por Nexia no pueden imponerse sobre esas llamadas externas.

Para Codex, el cliente genera un token `nxa_...`, define
`NEXIA_API_KEY=nxa_TU_TOKEN` y registra Nexia en
`%USERPROFILE%\.codex\config.toml`:

```toml
model = "claude-sonnet-4-6"
model_provider = "nexia"

[model_providers.nexia]
name = "Nexia"
base_url = "https://tu-dominio.com/v1"
env_key = "NEXIA_API_KEY"
wire_api = "responses"
requires_openai_auth = false
```

El endpoint Responses traduce mensajes y llamadas de herramientas a
`POST {API_BASE_URL}/chat/completions`. La ejecución de herramientas requiere que el
proveedor subyacente acepte herramientas en su formato compatible con OpenAI.

## Saldo de la API

La configuración muestra únicamente el balance o cuota real de la clave `sk-...`
asignada al cliente, consultado desde el servidor mediante `GET {API_BASE_URL}/usage`.

La clave MWAPI se descifra para las llamadas del servidor y también puede ser solicitada
explícitamente por su dueño autenticado para conectarla a Claude Code. Nunca se entrega
la clave compartida de prueba. Las cuentas gratuitas que usan esa prueba tampoco pueden
consultar su saldo global.

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
