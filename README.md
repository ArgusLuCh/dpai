# Registro de Actuaciones

Aplicación Flask para registrar actuaciones, allanamientos y oficios judiciales por usuario, con roles de administrador, consulta y actuario, y una vista de estadísticas.

## Stack

- Backend + frontend: Flask (server-side rendering con Jinja2)
- Base de datos: PostgreSQL
- Autenticación: Flask-Login
- Deploy: Railway

## Desarrollo local

1. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
2. Copiar `.env.example` a `.env` y completar `SECRET_KEY` y `DATABASE_URL` (podés usar una Postgres local o una instancia de Railway).
3. Ejecutar:
   ```bash
   python app.py
   ```
4. Abrir `http://127.0.0.1:5000`

## Primer uso

1. Ir a `/crear-admin` y crear la primera cuenta de administrador (hasta 3 admins en total).
2. Iniciar sesión con esa cuenta.
3. Los actuarios se registran desde `/login` → "Registrate aquí".

### Roles

- **Administrador**: ve y edita todas las actuaciones de todos los usuarios, gestiona usuarios, asigna estado/color.
- **Actuario**: carga y ve solo sus propios registros (actuaciones, allanamientos, oficios judiciales).
- **Consulta**: solo accede a la vista de estadísticas.

## Deploy en Railway

1. Crear un nuevo proyecto en Railway a partir de este repo de GitHub.
2. Agregar un servicio **PostgreSQL** al proyecto (Railway te da `DATABASE_URL` automáticamente).
3. En el servicio de la app, configurar las variables de entorno:
   - `SECRET_KEY` (clave aleatoria fuerte, no la del `.env.example`)
   - `FLASK_ENV=production`
   - `DATABASE_URL` (Railway la inyecta sola si conectás el servicio de Postgres)
4. Railway detecta el `Procfile` (`web: gunicorn app:app`) y lo usa como comando de arranque.
5. Al desplegar, `app.py` corre `init_db()` y `ensure_db_schema()` al iniciar, creando las tablas si no existen.

## Estructura

- `app.py` — lógica principal: rutas, autenticación, acceso a datos
- `templates/` — vistas Jinja2
- `static/` — CSS, íconos, logo
- `Procfile` — comando de arranque para Railway (gunicorn)
- `requirements.txt` — dependencias Python
