FROM python:3.13.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system coldsafe \
    && useradd --system --gid coldsafe --home-dir /app coldsafe

COPY backend/requirements.lock.txt /tmp/requirements.lock.txt
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements.lock.txt

COPY --chown=coldsafe:coldsafe backend /app/backend

USER coldsafe

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
