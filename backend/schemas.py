from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── Group ────────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    auto_sync: bool = False


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    auto_sync: Optional[bool] = None


class GroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    auto_sync: bool = False
    account_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# ── Account ──────────────────────────────────────────────

class AccountCreate(BaseModel):
    email: str
    password: str
    client_id: Optional[str] = None
    refresh_token: Optional[str] = None
    group_id: Optional[int] = None


class AccountResponse(BaseModel):
    id: int
    email: str
    status: str
    unread_count: int
    refresh_token: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    imap_enabled: Optional[bool] = None
    pop3_enabled: Optional[bool] = None
    graph_enabled: Optional[bool] = None
    last_synced: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AccountUpdateGroup(BaseModel):
    group_id: Optional[int] = None


class BatchImportRequest(BaseModel):
    text: str  # raw text, one account per line
    group_id: Optional[int] = None


class BatchImportResult(BaseModel):
    total: int
    success: int
    failed: int
    errors: List[str]


# ── Email ────────────────────────────────────────────────

class EmailAddress(BaseModel):
    name: Optional[str] = None
    address: str


class EmailSummary(BaseModel):
    id: str
    subject: Optional[str] = None
    sender: Optional[EmailAddress] = None
    received_at: Optional[str] = None
    is_read: bool = False
    preview: Optional[str] = None


class EmailDetail(BaseModel):
    id: str
    subject: Optional[str] = None
    sender: Optional[EmailAddress] = None
    to_recipients: List[EmailAddress] = []
    received_at: Optional[str] = None
    is_read: bool = False
    body_html: Optional[str] = None
    has_attachments: bool = False


class EmailListResponse(BaseModel):
    emails: List[EmailSummary]
    total: int


class SyncStatus(BaseModel):
    account_id: int
    email: str
    new_count: int


# ── Search ──────────────────────────────────────────────

class LocalEmailSummary(BaseModel):
    id: int
    account_id: int
    account_email: str
    message_id: str
    subject: Optional[str] = None
    sender_name: Optional[str] = None
    sender_address: Optional[str] = None
    received_at: Optional[datetime] = None
    is_read: bool = False
    body_preview: Optional[str] = None

    class Config:
        from_attributes = True


class SearchEmailResponse(BaseModel):
    results: List[LocalEmailSummary]
    total: int
