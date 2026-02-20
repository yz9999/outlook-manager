from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime, timedelta

from database import get_session
from models import Account, Email, Group
from schemas import EmailSummary, EmailDetail, EmailListResponse, EmailAddress, LocalEmailSummary, SearchEmailResponse
from outlook_client import outlook_client, ProxyError

router = APIRouter(prefix="/api", tags=["emails"])


# ── Helper ──────────────────────────────────────────────

async def _ensure_token(account: Account, session: AsyncSession, proxy_url: str = None):
    """Make sure access_token is valid; refresh if expired or missing."""
    needs_refresh = (
        not account.access_token
        or not account.token_expires_at
        or account.token_expires_at <= datetime.utcnow()
    )
    if needs_refresh:
        token_data = await outlook_client.refresh_access_token(
            account.client_id, account.refresh_token, proxy_url=proxy_url
        )
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data["refresh_token"]
        account.token_expires_at = datetime.utcnow() + timedelta(
            seconds=token_data["expires_in"]
        )
        await session.commit()


async def _get_proxy_url(account: Account, session: AsyncSession) -> Optional[str]:
    """Get the proxy URL from the account's group, if set."""
    if not account.group_id:
        return None
    result = await session.execute(
        select(Group).where(Group.id == account.group_id)
    )
    group = result.scalar_one_or_none()
    return group.proxy_url if group else None


def _parse_sender(msg: dict) -> Optional[EmailAddress]:
    fr = msg.get("from")
    if fr and fr.get("emailAddress"):
        ea = fr["emailAddress"]
        return EmailAddress(name=ea.get("name"), address=ea.get("address", ""))
    return None


# ── Email list: Graph API → IMAP(新) → IMAP(旧) → local DB ───

@router.get("/accounts/{account_id}/emails", response_model=EmailListResponse)
async def list_emails(
    account_id: int,
    top: int = Query(30, ge=1, le=100),
    skip: int = Query(0, ge=0),
    folder: str = Query("inbox", description="邮件文件夹: inbox, junkemail, deleteditems"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    proxy_url = await _get_proxy_url(account, session)
    errors = []

    # ── Try Graph API first ──
    if account.refresh_token and account.client_id:
        try:
            await _ensure_token(account, session, proxy_url=proxy_url)
            data = await outlook_client.fetch_emails(
                account.access_token, top=top, skip=skip,
                folder=folder, proxy_url=proxy_url
            )
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
            return EmailListResponse(emails=emails, total=total, method="Graph API")
        except ProxyError as e:
            # Proxy error: don't fall back to IMAP
            raise HTTPException(502, f"代理连接错误: {e}")
        except Exception as e:
            errors.append(f"Graph API: {e}")

    # ── Try IMAP (only for inbox folder) ──
    if account.client_id and account.refresh_token and folder == "inbox":
        try:
            data = await outlook_client.fetch_emails_imap(
                account.email, account.password,
                account.client_id, account.refresh_token,
                top=top
            )
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
            method = data.get("_method", "IMAP")
            return EmailListResponse(emails=emails, total=total, method=method)
        except Exception as e:
            errors.append(str(e))

    # ── Fallback: read from local DB ──
    count_q = select(func.count()).where(Email.account_id == account_id)
    total_result = await session.execute(count_q)
    total = total_result.scalar() or 0

    q = (
        select(Email)
        .where(Email.account_id == account_id)
        .order_by(Email.received_at.desc())
        .offset(skip)
        .limit(top)
    )
    result = await session.execute(q)
    db_emails = result.scalars().all()

    emails = []
    for e in db_emails:
        emails.append(
            EmailSummary(
                id=e.message_id,
                subject=e.subject,
                sender=EmailAddress(name=e.sender_name or "", address=e.sender_address or ""),
                received_at=e.received_at.isoformat() if e.received_at else None,
                is_read=e.is_read,
                preview=e.body_preview or "",
            )
        )

    if total > 0:
        return EmailListResponse(emails=emails, total=total, method="Local DB")

    # All methods failed, return error details
    if errors:
        raise HTTPException(
            502,
            detail={
                "message": "所有 API 方式均失败",
                "errors": errors,
            }
        )

    return EmailListResponse(emails=emails, total=total, method="Local DB")


# ── Email detail: Graph API → local DB fallback ────────

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

    proxy_url = await _get_proxy_url(account, session)

    # ── Try Graph API first ──
    if account.refresh_token and account.client_id:
        try:
            await _ensure_token(account, session, proxy_url=proxy_url)
            msg = await outlook_client.fetch_email_detail(
                account.access_token, message_id, proxy_url=proxy_url
            )

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
        except ProxyError as e:
            raise HTTPException(502, f"代理连接错误: {e}")
        except Exception:
            pass  # Fall through to local DB

    # ── Fallback: local DB ──
    result = await session.execute(
        select(Email).where(
            Email.account_id == account_id,
            Email.message_id == message_id
        )
    )
    email_record = result.scalar_one_or_none()
    if not email_record:
        raise HTTPException(404, "邮件不存在")

    return EmailDetail(
        id=email_record.message_id,
        subject=email_record.subject,
        sender=EmailAddress(
            name=email_record.sender_name or "",
            address=email_record.sender_address or ""
        ),
        to_recipients=[],
        received_at=email_record.received_at.isoformat() if email_record.received_at else None,
        is_read=email_record.is_read,
        body_html=f"<pre>{email_record.body_preview or '邮件内容需要通过 IMAP 获取完整正文'}</pre>",
        has_attachments=False,
    )


# ── Delete emails ───────────────────────────────────────

@router.delete("/accounts/{account_id}/emails/{message_id}")
async def delete_email(
    account_id: int,
    message_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete an email via Graph API."""
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    proxy_url = await _get_proxy_url(account, session)

    if account.refresh_token and account.client_id:
        try:
            await _ensure_token(account, session, proxy_url=proxy_url)
            ok = await outlook_client.delete_email(
                account.access_token, message_id, proxy_url=proxy_url
            )
            if ok:
                return {"message": "邮件已删除"}
            raise HTTPException(400, "删除失败")
        except ProxyError as e:
            raise HTTPException(502, f"代理连接错误: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"删除失败: {e}")
    else:
        raise HTTPException(400, "账号未配置 Graph API 凭证，无法删除")


@router.post("/accounts/{account_id}/emails/batch-delete")
async def batch_delete_emails(
    account_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    """Batch delete emails via Graph API."""
    message_ids = payload.get("message_ids", [])
    if not message_ids:
        raise HTTPException(400, "请选择要删除的邮件")

    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    proxy_url = await _get_proxy_url(account, session)

    if not (account.refresh_token and account.client_id):
        raise HTTPException(400, "账号未配置 Graph API 凭证，无法删除")

    await _ensure_token(account, session, proxy_url=proxy_url)

    success_count = 0
    fail_count = 0
    for mid in message_ids:
        try:
            ok = await outlook_client.delete_email(
                account.access_token, mid, proxy_url=proxy_url
            )
            if ok:
                success_count += 1
            else:
                fail_count += 1
        except Exception:
            fail_count += 1

    return {
        "message": f"删除完成: 成功 {success_count}, 失败 {fail_count}",
        "success_count": success_count,
        "fail_count": fail_count,
    }


# ── Local email search ──────────────────────────────────

@router.get("/emails/search", response_model=SearchEmailResponse)
async def search_emails(
    keyword: str = Query("", description="搜索主题关键词"),
    account_email: str = Query("", description="搜索账号邮箱"),
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

    if account_email.strip():
        q = q.where(Account.email.ilike(f"%{account_email.strip()}%"))

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
