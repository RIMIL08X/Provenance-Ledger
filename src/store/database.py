"""Database connection and session management supporting PostgreSQL and auto-falling back to SQLite for zero-config deployments."""

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
    """Get database URL from environment or return default."""
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def get_engine(url: str | None = None) -> Engine:
    """Create SQLAlchemy engine with automatic fallback for zero-config deployments."""
    db_url = url or get_database_url()
    try:
        engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        # Test connection
        with engine.connect() as conn:
            pass
        return engine
    except Exception:
        # Fallback to zero-config SQLite for single-shot cloud deployment (e.g. Hugging Face Spaces)
        fallback_url = "sqlite:///provenance_ledger.db"
        return create_engine(fallback_url, echo=False)


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
    """Create all tables in the active database."""
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
