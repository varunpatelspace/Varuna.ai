"""
Database connection and session management for VARUNA AI.
Supports both SQLite (for local development/testing) and PostgreSQL (for production).
Enforces foreign key constraints on SQLite connections.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator
import sqlite3

from app.config import settings

# Engine configuration with connection pooling
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False
)

# Enforce SQLite foreign key constraints
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for yielding database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
