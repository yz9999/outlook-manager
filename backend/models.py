from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from database import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(String(500), nullable=True)
    auto_sync = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    accounts = relationship("Account", back_populates="group", lazy="selectin")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    client_id = Column(String(255), nullable=True)
    refresh_token = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="active")  # active / error / syncing
    last_synced = Column(DateTime, nullable=True)
    unread_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("Group", back_populates="accounts", lazy="selectin")
    emails = relationship("Email", back_populates="account", cascade="all, delete-orphan", lazy="noload")


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("account_id", "message_id", name="uq_account_message"),
        Index("ix_emails_subject", "subject"),
        Index("ix_emails_received_at", "received_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=True)
    sender_name = Column(String(255), nullable=True)
    sender_address = Column(String(255), nullable=True)
    received_at = Column(DateTime, nullable=True)
    is_read = Column(Boolean, default=False)
    body_preview = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="emails", lazy="selectin")
