"""
init_db.py
Creates all tables via SQLAlchemy create_all().
Run once on startup or manually: uv run python -m app.db.init_db
"""
import os

from app.db.connection import Base, engine
from app.db import models  # noqa: F401 — import models so Base knows about them


def init_db() -> None:
    """Create all tables. Safe to call multiple times (CREATE IF NOT EXISTS)."""
    # Ensure data/ directory exists (SQLite needs the folder to exist)
    db_path = engine.url.database
    if db_path and db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    Base.metadata.create_all(bind=engine)
    print(f"[init_db] Tables created at: {engine.url}")


if __name__ == "__main__":
    init_db()
