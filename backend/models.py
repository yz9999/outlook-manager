from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from database import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(String(500), nullable=True)
    color = Column(String(50), nullable=True)
    proxy_url = Column(String(500), nullable=True)
    auto_sync = Column(Boolean, default=False, nullable=False)
    sync_interval_minutes = Column(Integer, default=2, nullable=False)
    sync_batch_size = Column(Integer, default=1, nullable=False)
    auto_refresh_token = Column(Boolean, default=True, nullable=False)
    refresh_interval_hours = Column(Integer, default=24, nullable=False)
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
    imap_enabled = Column(Boolean, nullable=True, default=None)
    pop3_enabled = Column(Boolean, nullable=True, default=None)
    graph_enabled = Column(Boolean, nullable=True, default=None)
    remark = Column(String(500), nullable=True)
    last_refresh_at = Column(DateTime, nullable=True)
    refresh_status = Column(String(50), default="unknown")  # unknown / success / failed
    sync_method = Column(String(50), nullable=True)  # graph / imap_new / imap_old
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("Group", back_populates="accounts", lazy="selectin")
    emails = relationship("Email", back_populates="account", cascade="all, delete-orphan", lazy="noload")
    refresh_logs = relationship("RefreshLog", back_populates="account", cascade="all, delete-orphan", lazy="noload")


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


class RefreshLog(Base):
    __tablename__ = "refresh_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    account_email = Column(String(255), nullable=False)
    refresh_type = Column(String(50), nullable=False)  # manual / auto / retry
    status = Column(String(50), nullable=False)  # success / failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="refresh_logs", lazy="selectin")
