# Nexia AI

Plataforma multiusuario de chat con IA, construida con FastAPI. Cada cliente tiene
su propia cuenta, conversaciones independientes, saldo de créditos y registro de
consumo. La API key de cada cliente permanece cifrada en el servidor.

## Funciones

- Registro con nombre, correo y contraseña.
- Inicio de sesión con Google mediante OAuth 2.0.
- Apartado de chats con conversaciones separadas, historial y eliminación.
- Streaming de respuestas desde una API compatible con OpenAI.
- Modelos incluidos exactamente como aparecen en API Usage Guide.pdf.
- Página Mi cuenta con créditos asignados, usados, disponibles y actividad reciente.
- Prueba gratuita diaria opcional mediante una clave compartida.
- Panel de administración para activar clientes, guardar su API key y recargar créditos.
- Sesiones firmadas con vencimiento, protección CSRF y claves API cifradas con Fernet.
- SQLite para desarrollo y PostgreSQL para producción.

## Cómo funciona el saldo

Nexia mantiene un saldo interno por cliente:

- Una respuesta completada consume 1 crédito.
- Si el proveedor falla, la reserva se devuelve y el evento de consumo se elimina.
- El administrador asigna créditos y el cliente ve el saldo actualizado después de cada chat.
- La guía del proveedor no documenta un endpoint de balance. El saldo externo de
  mwapi.dev se consulta manualmente en https://api.mwapi.dev/reseller.

Por tanto, los créditos de Nexia son el control comercial de la plataforma y no una lectura
automática del saldo externo del proveedor.

## Ejecutar localmente

Requiere Python 3.12.

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
~~~

La aplicación carga automáticamente las variables de .env. Ejecuta:

~~~powershell
uvicorn app.main:app --reload
~~~

Abre http://localhost:8000.

Para disponer del panel administrativo, define ADMIN_EMAIL y ADMIN_PASSWORD antes
del primer arranque. FIRST_USER_IS_ADMIN permanece en false por seguridad.

## Configurar acceso con Google

1. En Google Cloud Console crea o selecciona un proyecto.
2. Configura la pantalla de consentimiento OAuth.
3. Crea un ID de cliente OAuth de tipo Aplicación web.
4. Añade estos URI de redirección autorizados:
   - Local: http://localhost:8000/auth/google/callback
   - Producción: https://tu-dominio.com/auth/google/callback
5. Copia el ID y secreto a GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET.
6. Define APP_BASE_URL con el origen público, sin barra final.

Si esas variables no están configuradas, el formulario de acceso continúa funcionando
con correo y contraseña y muestra una indicación de configuración.

## Variables de entorno

| Variable | Uso |
| --- | --- |
| SECRET_KEY | Firma sesiones, CSRF y estados OAuth. Debe ser larga y aleatoria. |
| API_KEY_ENCRYPTION_KEY | Cifra API keys. Debe conservarse estable entre despliegues. |
| DATABASE_URL | URL de SQLite o PostgreSQL. |
| ADMIN_EMAIL / ADMIN_PASSWORD | Crea o asciende al administrador inicial. |
| FIRST_USER_IS_ADMIN | Solo desarrollo. Convierte el primer registro en admin si vale true. |
| API_BASE_URL | Por defecto https://api.mwapi.dev/v1. |
| TRIAL_API_KEY | Clave compartida para la prueba gratuita opcional. |
| DAILY_MESSAGE_LIMIT | Mensajes gratuitos diarios por cliente. |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | Credenciales OAuth web de Google. |
| APP_BASE_URL | Origen público usado para el callback de Google. |
| COOKIE_SECURE | Debe valer true en producción HTTPS. |

## Modelos documentados

- claude-haiku-4-5-20251001
- claude-opus-4-6
- claude-opus-4-7
- claude-opus-4-8
- claude-opus-5
- claude-sonnet-4-6
- claude-sonnet-5

Las solicitudes se envían a POST {API_BASE_URL}/chat/completions con streaming SSE.

## Desplegar en Render

1. Sube el proyecto a GitHub.
2. En Render elige New → Blueprint y selecciona el repositorio.
3. render.yaml crea el servicio web y PostgreSQL.
4. Completa ADMIN_EMAIL, ADMIN_PASSWORD, TRIAL_API_KEY (opcional),
   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET y APP_BASE_URL.
5. Añade el callback público a los URI autorizados de Google y despliega.

No cambies SECRET_KEY ni API_KEY_ENCRYPTION_KEY después de guardar claves de clientes:
invalidaría sesiones o impediría descifrar las claves ya almacenadas.

## Estructura

~~~text
app/
  main.py       rutas, Google OAuth, páginas y proxy de chat
  models.py     tablas y migraciones aditivas
  security.py   sesiones, CSRF, contraseñas y cifrado
  usage.py      prueba, créditos, reservas y devoluciones
templates/
  chat.html     chats e historial por conversación
  account.html  saldo y actividad de cada cliente
  admin.html    configuración y gestión de clientes
static/
  styles.css
~~~

Al iniciar, Nexia aplica migraciones aditivas y agrupa mensajes de versiones anteriores
en una conversación titulada “Conversación anterior”; no borra el historial existente.
