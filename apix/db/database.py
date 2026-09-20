"""Database connection and engine setup for APIx (PostgreSQL with SQLite fallback)."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from apix.config import DATA_DIR

# Base directory for database file when using SQLite fallback
DB_PATH = DATA_DIR / "apix.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Default to SQLite fallback if DATABASE_URL environment variable is not provided
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# SQLite specific connect args
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency / context manager generator for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initializes database schema tables."""
    Base.metadata.create_all(bind=engine)
