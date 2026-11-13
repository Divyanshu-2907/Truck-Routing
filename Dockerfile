# One image that serves both halves of the app: Django handles /api/, and
# the React build is served as static files from the same origin. Because
# there is only one origin in production, no CORS is involved.

# ---------------------------------------------------------------------------
# Stage 1: build the React app with Node. None of this ends up in the final
# image - only the built files are copied across.
# ---------------------------------------------------------------------------
FROM node:20 AS frontend

WORKDIR /app/frontend

# Dependencies are copied first so Docker can reuse the cached install layer
# whenever only the source has changed.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: the Python image that actually runs.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# The React build lands where settings.py expects it. WhiteNoise serves this
# folder at the site root, so /assets/... and / both work.
COPY --from=frontend /app/frontend/dist ./frontend_dist

# Gathers Django's own static files (the REST framework's styling) into
# staticfiles/ so WhiteNoise can serve them too.
# Settings refuse to load without a secret key when DEBUG is off, so this
# one build step gets a throwaway key. It only exists for this command and is
# not baked into the image; the real key is supplied when the container runs.
RUN DJANGO_SECRET_KEY=build-only-collectstatic python manage.py collectstatic --noinput

# Writes .gz and .br copies of the React bundles next to the originals.
# WhiteNoise then serves the compressed one, which takes the main bundle
# from about 750 kB down to about 230 kB on the wire.
RUN python -m whitenoise.compress frontend_dist

EXPOSE 8000

# Render supplies $PORT, so the command runs through a shell to expand it.
# The JSON form keeps Docker's signal handling predictable on shutdown.
#
# One process with eight threads rather than several processes: the work is
# almost all waiting on external APIs, which threads handle well, and a
# single process means one shared cache and one Nominatim rate limiter.
# With two processes each would keep its own, so the heatmap request could
# miss the routes the plan request had just cached, and the app could send
# Nominatim two requests a second instead of one.
#
# The timeout is generous because one request waits on two external APIs.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 120 --access-logfile -"]
