from sqlalchemy import Column, String, Boolean
from database import Base

class Book(Base):
    __tablename__ = "books"

    ean = Column(String, primary_key=True, index=True)
    author = Column(String)
    title = Column(String)
    takedown = Column(Boolean, default=False)
    release_date = Column(String, nullable=True)
    abridged_status = Column(String, nullable=True)
    narrator = Column(String, nullable=True)
    description = Column(String, nullable=True)
