# Organizador de Eventos - Backend

API del proyecto Organizador de Eventos Independientes (Equipo 6). Está hecha con Django REST Framework y guarda los datos en una base PostgreSQL en Supabase.

- API desplegada: https://eventflow-back.onrender.com
- Documentación (Swagger): https://eventflow-back.onrender.com/api/docs/
- Frontend: https://eventflow-front-two.vercel.app

## Correrlo en local

Se necesita Python 3.10 o superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

Queda en http://127.0.0.1:8000 y la documentación en http://127.0.0.1:8000/api/docs/.

Las tablas ya existen en Supabase, por eso el proyecto no tiene migraciones propias. Sin `DATABASE_URL` arranca con una base SQLite vacía: sirve para ver la documentación, pero no para guardar datos.

## Variables de entorno

Van en un archivo `.env` en la raíz (no se sube al repo) o en el panel de Render.

| Variable | Para qué |
| --- | --- |
| `SECRET_KEY` | Llave con la que se firman los tokens de sesión. |
| `DEBUG` | `True` solo en local. |
| `DATABASE_URL` | Conexión a la base de Supabase. |
| `ALLOWED_HOSTS` | Direcciones del backend, separadas por coma y sin `https://`. |
| `CORS_ALLOWED_ORIGINS` | Sitios que pueden llamar a la API, separados por coma y con `https://`. |
| `CSRF_TRUSTED_ORIGINS` | Igual que la anterior. |

## Pruebas

```bash
python manage.py test
```

Corren sobre una base temporal, no tocan la de Supabase.

## Endpoints

El detalle de cada uno, con ejemplos, está en Swagger. Todos menos `health` y `login` piden el encabezado `Authorization: Bearer <token>`.

| Método | Ruta | Qué hace |
| --- | --- | --- |
| GET | `/api/health/` | Comprueba que la API está viva |
| POST | `/api/login/` | Inicia sesión y devuelve el token |
| GET | `/api/organizador/me/` | Datos del organizador |
| GET, PUT | `/api/organizador/limite-diario/` | Ver o cambiar el límite diario de horas (6 por defecto, de 1 a 16) |
| GET, POST | `/api/eventos/` | Listar o crear eventos |
| GET, PUT, PATCH, DELETE | `/api/eventos/<id>/` | Ver, editar o eliminar un evento |
| GET, POST | `/api/eventos/<id>/subtareas/` | Listar o agregar gestiones de un evento |
| GET, PUT, PATCH, DELETE | `/api/subtareas/<id>/` | Ver, editar, reprogramar o eliminar una gestión |
| GET | `/api/subtareas/hoy/` | Gestiones agrupadas en vencidas, para hoy y próximas |

Al editar o reprogramar una gestión, si el día queda por encima del límite diario la API no guarda y responde 409 con las cifras y fechas sugeridas.
