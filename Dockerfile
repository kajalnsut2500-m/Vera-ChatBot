FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app/ ./app/

RUN pip install --no-cache-dir -e .

# Default DB path; override with VERA_DB_PATH env var (e.g. /data/vera.db on Railway)
ENV VERA_DB_PATH=./vera.db

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
