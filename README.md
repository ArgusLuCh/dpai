# Registro de Actuaciones (DPAI)

App Flask para que los administradores carguen actuaciones, allanamientos y oficios judiciales, y para compartir un link público con las estadísticas actualizadas.

## Stack

Flask + Jinja2, Flask-Login, PostgreSQL (Neon), deploy en Railway (`Procfile` → gunicorn).

## Variables de entorno

| Variable | Uso |
|---|---|
| `DATABASE_URL` | Cadena de conexión a Postgres |
| `SECRET_KEY` | Clave de sesión (obligatoria con `FLASK_ENV=production`) |
| `STATS_TOKEN` | Token del link público de estadísticas |
| `FLASK_ENV` | `production` en Railway |

Generar valores: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Usuarios

No hay registro público. Los admins se crean por consola (con `DATABASE_URL` apuntando a la base):

```bash
flask --app app crear-admin nombre_usuario --nombre "Nombre Apellido"
```

Si el usuario ya existe, le da rol admin y cambia su contraseña. Solo los admins pueden iniciar sesión.

## Link de estadísticas

`https://<tu-app>/estadisticas/<STATS_TOKEN>` — sin login, solo lectura. Para invalidar el link, cambiá `STATS_TOKEN`. Al iniciar sesión, la pestaña **Estadísticas** muestra el link completo.

## Desarrollo local

```bash
pip install -r requirements.txt
cp .env.example .env   # completar valores
python app.py
```

## Estructura

- `app.py` — rutas, autenticación y acceso a datos
- `templates/` — vistas Jinja2 (`_form_actuacion.html` es el formulario compartido)
- `static/` — CSS, logo y favicon
- `Procfile`, `requirements.txt`
