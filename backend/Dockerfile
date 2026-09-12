FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

# Run as a non-root user. The upload dirs are created up-front and handed to
# that user, since the app writes photos/avatars under /app/uploads at runtime
# (routers/calendar.py, routers/pets.py, routers/auth.py).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads/photos /app/uploads/avatars /app/uploads/users \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
