from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

DATABASE_URL = settings.DATABASE_URL

# CRITICAL: SQLAlchemy v2 rejects "postgres://" — must be "postgresql://"
# Supabase and some cloud providers return "postgres://" which must be fixed.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Check if we are using SQLite
is_sqlite = DATABASE_URL.startswith("sqlite")

connect_args = {}
if is_sqlite:
    # SQLite requires check_same_thread=False for multi-threaded applications like FastAPI
    connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    # PostgreSQL (Supabase/Render): use connection pool settings
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Detect stale connections
        pool_recycle=300,    # Recycle connections every 5 minutes
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# FastAPI Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
