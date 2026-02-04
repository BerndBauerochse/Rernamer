import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Allow override via ENV, default to /app/data/metadata.db
DB_PATH = os.getenv("DB_PATH", "/app/data/metadata.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# Ensure dir exists if local testing
if os.name == 'nt' and not os.path.exists(os.path.dirname(DB_PATH)) and "/app/" not in DB_PATH:
     os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
