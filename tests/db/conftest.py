"""Database test fixtures — Postgres via Testcontainers."""

import os
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

# Docker Desktop on macOS uses a non-standard socket path
_DOCKER_SOCK = Path.home() / ".docker/run/docker.sock"
if not os.environ.get("DOCKER_HOST") and _DOCKER_SOCK.exists():
    os.environ["DOCKER_HOST"] = f"unix://{_DOCKER_SOCK}"


@pytest.fixture(scope="session")
def pg_container():
    """Spin up a throwaway Postgres container for the test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        os.environ["DATABASE_URL"] = pg.get_connection_url(driver=None)
        from video_to_essay.db import init_db

        init_db()
        yield pg


@pytest.fixture(autouse=True)
def clean_tables(pg_container):
    """Truncate all tables between tests for isolation."""
    yield
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "TRUNCATE deliveries, subscriptions, videos, channels, users CASCADE"
        )
        conn.commit()


@pytest.fixture()
def raw_conn(pg_container):
    """Raw psycopg connection for direct SQL in test setup."""
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        yield conn
