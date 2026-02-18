from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime, timedelta

from database import get_session
from models import Account, Email
from schemas import EmailSummary, EmailDetail, EmailListResponse, EmailAddress, LocalEmailSummary, SearchEmailResponse
from outlook_client import outlook_client

router = APIRouter(prefix="/api", tags=["emails"])


# ── Online email fetching (existing) ────────────────────

async def _ensure_token(account: Account, session: AsyncSession):
    """Make sure access_token is valid; refresh if expired or missing."""
    needs_refresh = (
        not account.access_token
        or not account.token_expires_at
        or account.token_expires_at <= datetime.utcnow()
    )
    if needs_refresh:
        token_data = await outlook_client.refresh_access_token(
            account.client_id, account.refresh_token
        )
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data["refresh_token"]
        account.token_expires_at = datetime.utcnow() + timedelta(
            seconds=token_data["expires_in"]
        )
        await session.commit()


def _parse_sender(msg: dict) -> Optional[EmailAddress]:
    fr = msg.get("from")
    if fr and fr.get("emailAddress"):
        ea = fr["emailAddress"]
        return EmailAddress(name=ea.get("name"), address=ea.get("address", ""))
    return None


@router.get("/accounts/{account_id}/emails", response_model=EmailListResponse)
async def list_emails(
    account_id: int,
    top: int = Query(30, ge=1, le=100),
    skip: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    try:
        await _ensure_token(account, session)
        data = await outlook_client.fetch_emails(
            account.access_token, top=top, skip=skip
        )
    except Exception as e:
        raise HTTPException(500, f"获取邮件失败: {str(e)[:200]}")

    emails = []
    for msg in data.get("value", []):
        emails.append(
            EmailSummary(
                id=msg["id"],
                subject=msg.get("subject"),
                sender=_parse_sender(msg),
                received_at=msg.get("receivedDateTime"),
                is_read=msg.get("isRead", False),
                preview=msg.get("bodyPreview", "")[:200],
            )
        )

    total = data.get("@odata.count", len(emails))
    return EmailListResponse(emails=emails, total=total)


@router.get("/accounts/{account_id}/emails/{message_id}", response_model=EmailDetail)
async def get_email_detail(
    account_id: int,
    message_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    try:
        await _ensure_token(account, session)
        msg = await outlook_client.fetch_email_detail(
            account.access_token, message_id
        )
    except Exception as e:
        raise HTTPException(500, f"获取邮件详情失败: {str(e)[:200]}")

    to_list = []
    for r in msg.get("toRecipients", []):
        ea = r.get("emailAddress", {})
        to_list.append(EmailAddress(name=ea.get("name"), address=ea.get("address", "")))

    body = msg.get("body", {})

    return EmailDetail(
        id=msg["id"],
        subject=msg.get("subject"),
        sender=_parse_sender(msg),
        to_recipients=to_list,
        received_at=msg.get("receivedDateTime"),
        is_read=msg.get("isRead", False),
        body_html=body.get("content") if body.get("contentType") == "html" else f"<pre>{body.get('content', '')}</pre>",
        has_attachments=msg.get("hasAttachments", False),
    )


# ── Local email search ──────────────────────────────────

@router.get("/emails/search", response_model=SearchEmailResponse)
async def search_emails(
    keyword: str = Query("", description="搜索主题关键词"),
    group_id: int = Query(None, description="按分组筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Search locally saved emails by subject keyword, optionally filtered by group."""
    q = select(Email).join(Account, Email.account_id == Account.id)

    if group_id is not None:
        q = q.where(Account.group_id == group_id)

    if keyword.strip():
        q = q.where(Email.subject.ilike(f"%{keyword.strip()}%"))

    # Count total
    count_q = select(func.count()).select_from(q.subquery())
    total_result = await session.execute(count_q)
    total = total_result.scalar() or 0

    # Fetch page
    q = q.order_by(Email.received_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(q)
    emails = result.scalars().all()

    results = []
    for e in emails:
        results.append(LocalEmailSummary(
            id=e.id,
            account_id=e.account_id,
            account_email=e.account.email if e.account else "",
            message_id=e.message_id,
            subject=e.subject,
            sender_name=e.sender_name,
            sender_address=e.sender_address,
            received_at=e.received_at,
            is_read=e.is_read,
            body_preview=e.body_preview,
        ))

    return SearchEmailResponse(results=results, total=total)


@router.patch("/emails/{email_id}/mark-read")
async def mark_email_read(email_id: int, session: AsyncSession = Depends(get_session)):
    """Mark a locally saved email as read."""
    result = await session.execute(select(Email).where(Email.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(404, "邮件不存在")
    email.is_read = True
    await session.commit()
    return {"message": "ok"}

