FROM python:3.11-slim

RUN groupadd --system peach && useradd --system --gid peach --no-create-home peach

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/backend/
COPY config/ /app/config/
COPY alembic.ini /app/alembic.ini

RUN mkdir -p /app/data /app/profiles /app/images && \
    chown -R peach:peach /app

USER peach

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
