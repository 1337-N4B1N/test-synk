#!/bin/sh
set -e

echo "Waiting for MySQL at ${DB_HOST:-localhost}:${DB_PORT:-3306}..."
while ! nc -z "${DB_HOST:-localhost}" "${DB_PORT:-3306}"; do
  sleep 0.5
done
echo "MySQL is up."

python manage.py makemigrations submissions --noinput
python manage.py migrate --noinput

# For a learning demo we run the Django dev server (auto-reload, nice errors).
# Swap to gunicorn for a production-like run:
#   gunicorn config.wsgi:application --bind 0.0.0.0:8000
exec python manage.py runserver 0.0.0.0:8000
