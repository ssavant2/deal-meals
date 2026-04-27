"""
Database connection and session management.

SQLAlchemy = ORM (Object-Relational Mapping)
Instead of writing raw SQL, you work with Python objects.

Think of it like Entity Framework in .NET
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from loguru import logger

from config import settings
from models import Base  # Import from models.py to ensure single source of truth


# ===== ENGINE SETUP =====
# Engine = connection to the database
# Think of it like SqlConnection that you reuse
engine = create_engine(
    str(settings.database_url),

    # Connection pooling (keeps connections open for reuse)
    poolclass=QueuePool,
    pool_size=5,          # Max 5 connections in the pool
    max_overflow=10,      # Additional 10 if needed
    pool_pre_ping=True,   # Test connection before use (avoids "connection lost")
    pool_recycle=3600,    # Recycle connections after 1 hour (prevents stale connections)

    # Logging (set True to see all SQL queries)
    echo=settings.debug,
)

# ===== SESSION FACTORY =====
# SessionLocal = factory for creating database sessions
# A session = a "transaction" against the database
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,  # We want explicit commit (like BEGIN TRAN in SQL)
    autoflush=False,   # Wait with flush until we say so
    expire_on_commit=False,  # Don't expire objects after commit (allows use outside session)
)


# ===== CONTEXT MANAGER FOR SESSIONS =====
@contextmanager
def get_db_session():
    """
    Context manager for database sessions.

    Usage:
        with get_db_session() as session:
            products = session.query(Product).all()

    This is like using() in C#:
    - Creates a session
    - Yields it to your code
    - You must call session.commit() explicitly for writes
    - Rollback if something went wrong
    - Always closes the session (cleanup)
    """
    session = SessionLocal()
    try:
        yield session
    except Exception as e:
        session.rollback()  # Rollback on error
        logger.error(f"Database error, rolling back: {e}")
        raise  # Re-raise exception so caller sees the error
    finally:
        session.close()  # Always close the session


# ===== TEST FUNCTION =====
def test_connection():
    """
    Tests database connection.

    Returns True if connection works, False otherwise.
    """
    try:
        with get_db_session() as session:
            # Run a simple query (like SELECT 1 in SQL)
            session.execute(text("SELECT 1"))
            logger.success("Database connection OK")
            return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


# ===== INITIALIZE FUNCTION =====
def init_db():
    """
    Creates all tables defined in models.py

    NOTE: We don't use this since we have init.sql
    But good to have for dev/testing.
    """
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")


def shutdown_db():
    """Dispose engine and close all pooled connections on application shutdown."""
    engine.dispose()
    logger.info("Database connections closed")
