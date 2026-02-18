"""FastAPI dependency injection helpers."""

from sqlalchemy.orm import Session

from src.models.database import get_session_factory


def get_db_session() -> Session:
    """Get database session for dependency injection.

    Yields:
        SQLAlchemy database session

    Example:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db_session)):
            return db.query(Item).all()
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
