#!/usr/bin/env python3
"""
Docker Multi-Service Application
Backend: Python HTTP API
Database: PostgreSQL
Frontend: Node.js service
Infrastructure: Docker Compose, isolated network, persistent volume

Run:
    python app.py
    python app.py --scaffold
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

try:
    import psycopg
except ImportError:
    psycopg = None


SERVICE_NAME = "task-api"
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app_user:app_password@localhost:5432/taskdb"
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(SERVICE_NAME)


@dataclass
class Task:
    id: str
    title: str
    description: str
    status: str
    created_at: str


class ValidationError(Exception):
    pass


class DatabaseError(Exception):
    pass


class TaskRepository:
    """PostgreSQL persistence layer with explicit transaction boundaries."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._connection_lock = threading.Lock()

    def connect(self):
        if psycopg is None:
            raise DatabaseError("Install psycopg[binary] to use PostgreSQL.")
        return psycopg.connect(
            self.database_url,
            connect_timeout=5,
            application_name=SERVICE_NAME
        )

    def initialize(self):
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id UUID PRIMARY KEY,
                        title VARCHAR(200) NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        status VARCHAR(20) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','in_progress','completed')),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tasks_created_at
                    ON tasks(created_at DESC)
                """)

    def create(self, title: str, description: str = "") -> Task:
        task_id = str(uuid4())

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO tasks (id, title, description)
                    VALUES (%s, %s, %s)
                    RETURNING id, title, description, status, created_at
                """, (task_id, title, description))
                row = cursor.fetchone()

        return self._convert(row)

    def list_all(self) -> list[Task]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, title, description, status, created_at
                    FROM tasks
                    ORDER BY created_at DESC
                    LIMIT 500
                """)
                rows = cursor.fetchall()

        return [self._convert(row) for row in rows]

    def update_status(self, task_id: str, status: str) -> Task | None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE tasks
                    SET status = %s
                    WHERE id = %s
                    RETURNING id, title, description, status, created_at
                """, (status, task_id))
                row = cursor.fetchone()

        return self._convert(row) if row else None

    @staticmethod
    def _convert(row) -> Task:
        return Task(
            id=str(row[0]),
            title=row[1],
            description=row[2],
            status=row[3],
            created_at=row[4].isoformat()
        )


def validate_task(data: Any) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")

    title = data.get("title")
    description = data.get("description", "")

    if not isinstance(title, str) or not title.strip():
        raise ValidationError("Title is required.")

    if len(title.strip()) > 200:
        raise ValidationError("Title cannot exceed 200 characters.")

    if not isinstance(description, str) or len(description) > 5000:
        raise ValidationError("Invalid description.")

    return title.strip(), description.strip()


def scaffold_project(directory: str = "."):
    """Generate Dockerfiles and a Compose deployment configuration."""

    from pathlib import Path

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)

    files = {
        "requirements.txt": "psycopg[binary]>=3.2,<4\n",
        "Dockerfile.backend": """FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
RUN useradd --system --uid 10001 appuser
USER 10001
EXPOSE 8000
CMD ["python", "app.py"]
""",
        "Dockerfile.frontend": """FROM node:22-alpine
WORKDIR /app
COPY frontend.js .
RUN chown -R node:node /app
USER node
ENV PORT=3000
EXPOSE 3000
CMD ["node", "frontend.js"]
""",
        ".dockerignore": """__pycache__
.git
.env
.venv
node_modules
*.pyc
""",
        ".env.example": """POSTGRES_DB=taskdb
POSTGRES_USER=app_user
POSTGRES_PASSWORD=replace_with_a_strong_secret
DATABASE_URL=postgresql://app_user:replace_with_a_strong_secret@db:5432/taskdb
""",
        "compose.yaml": """services:
  db:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-taskdb}
      POSTGRES_USER: ${POSTGRES_USER:-app_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - backend_network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    restart: unless-stopped
    environment:
      PORT: "8000"
      DATABASE_URL: ${DATABASE_URL:?Set DATABASE_URL}
    depends_on:
      db:
        condition: service_healthy
    networks:
      - backend_network
      - frontend_network
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 5

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    restart: unless-stopped
    environment:
      PORT: "3000"
      API_URL: http://backend:8000
    ports:
      - "3000:3000"
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - frontend_network
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://localhost:3000/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]
      interval: 10s
      timeout: 3s
      retries: 5

networks:
  frontend_network:
    driver: bridge
  backend_network:
    driver: bridge
    internal: true

volumes:
  postgres_data:
    driver: local
""",
    }

    for filename, content in files.items():
        path = root / filename
        path.write_text(content, encoding="utf-8")
        logger.info("Generated %s", path)


class APIHandler(BaseHTTPRequestHandler):
    repository: TaskRepository | None = None

    def send_json(self, status: int, payload: Any):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            self.send_json(200, {
                "service": SERVICE_NAME,
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return

        if path == "/api/tasks":
            try:
                tasks = self.repository.list_all()
                self.send_json(200, {
                    "count": len(tasks),
                    "tasks": [asdict(task) for task in tasks]
                })
            except Exception:
                logger.exception("Task retrieval failed")
                self.send_json(503, {"error": "Database unavailable"})
            return

        self.send_json(404, {"error": "Route not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/tasks":
            self.send_json(404, {"error": "Route not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length <= 0 or length > 16384:
                raise ValidationError("Request size must be between 1 and 16384 bytes.")

            data = json.loads(self.rfile.read(length))
            title, description = validate_task(data)
            task = self.repository.create(title, description)

            self.send_json(201, asdict(task))

        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception:
            logger.exception("Task creation failed")
            self.send_json(503, {"error": "Database operation failed"})

    def do_PATCH(self):
        parts = urlparse(self.path).path.strip("/").split("/")

        if len(parts) != 3 or parts[:2] != ["api", "tasks"]:
            self.send_json(404, {"error": "Route not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise ValidationError("Invalid request size.")

            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValidationError("JSON object required.")

            status = data.get("status")
            if status not in {"pending", "in_progress", "completed"}:
                raise ValidationError("Unsupported task status.")

            task = self.repository.update_status(parts[2], status)

            if task is None:
                self.send_json(404, {"error": "Task not found"})
            else:
                self.send_json(200, asdict(task))

        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception:
            logger.exception("Task update failed")
            self.send_json(503, {"error": "Database operation failed"})

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)


def main():
    parser = argparse.ArgumentParser(description="Multi-service Docker application")
    parser.add_argument("--scaffold", action="store_true")
    args = parser.parse_args()

    if args.scaffold:
        scaffold_project()
        return

    repository = TaskRepository(DATABASE_URL)

    for attempt in range(10):
        try:
            repository.initialize()
            logger.info("PostgreSQL connection established.")
            break
        except Exception:
            logger.warning("Database connection attempt %d failed.", attempt + 1)
            if attempt == 9:
                raise
            time.sleep(min(2 ** attempt, 10))

    APIHandler.repository = repository
    server = ThreadingHTTPServer((HOST, PORT), APIHandler)
    server.daemon_threads = True

    def shutdown_handler(signum, frame):
        logger.info("Received shutdown signal.")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info("API listening on %s:%s", HOST, PORT)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        logger.info("API server stopped.")


if __name__ == "__main__":
    main()
