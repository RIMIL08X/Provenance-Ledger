"""Database connection and session management strictly for PostgreSQL."""

import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.store.models import Base

load_dotenv()

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/provenance_ledger"


def get_database_url() -> str:
    """Get PostgreSQL database URL from environment or return default."""
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    # Ensure postgresql scheme with psycopg
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def get_engine(url: str | None = None) -> Engine:
    """Create SQLAlchemy engine for PostgreSQL."""
    db_url = url or get_database_url()
    return create_engine(db_url, echo=False, pool_pre_ping=True)


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Create session factory for the engine."""
    eng = engine or get_engine()
    return sessionmaker(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Engine | None = None) -> None:
    """Create all tables in PostgreSQL."""
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
