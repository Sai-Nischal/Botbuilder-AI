from datetime import datetime
import json
from typing import Generator
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from app.config import DATABASE_URL

# SQLite connect args
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


    businesses = relationship("Business", back_populates="owner", cascade="all, delete-orphan")


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(String(100), unique=True, index=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=True)
    config = Column(Text, nullable=False, default="{}")
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="businesses")
    bot = relationship("Bot", back_populates="business", uselist=False, cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="business", cascade="all, delete-orphan")

    def get_config_dict(self) -> dict:
        try:
            return json.loads(self.config) if self.config else {}
        except Exception:
            return {}

    def set_config_dict(self, cfg: dict):
        self.config = json.dumps(cfg, ensure_ascii=False, indent=2)


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(String(100), ForeignKey("businesses.business_id", ondelete="CASCADE"), unique=True, nullable=False)
    mode = Column(String(20), default="shared")  # "shared" or "branded"
    bot_key = Column(String(100), unique=True, nullable=False, index=True)
    encrypted_token = Column(Text, nullable=True)
    bot_username = Column(String(100), nullable=True)
    secret_token = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="bot")


class ChatMapping(Base):
    __tablename__ = "chat_mappings"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String(100), default="shared", index=True)
    chat_id = Column(String(100), nullable=False, index=True)
    business_id = Column(String(100), ForeignKey("businesses.business_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("bot_id", "chat_id", name="uq_bot_chat"),
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(String(100), ForeignKey("businesses.business_id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="documents")
    passages = relationship("Passage", back_populates="document", cascade="all, delete-orphan")


class Passage(Base):
    __tablename__ = "passages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(String(100), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)

    document = relationship("Document", back_populates="passages")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
