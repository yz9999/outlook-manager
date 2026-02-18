from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta
from typing import List

from database import get_session
from models import Account
from schemas import (
    AccountCreate,
    AccountResponse,
    AccountUpdateGroup,
    BatchImportRequest,
    BatchImportResult,
)
from outlook_client import outlook_client

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=List[AccountResponse])
async def list_accounts(
    group_id: int = None,
    session: AsyncSession = Depends(get_session),
):
    q = select(Account)
    if group_id is not None:
        q = q.where(Account.group_id == group_id)
    q = q.order_by(Account.created_at.asc())
    result = await session.execute(q)
    accounts = result.scalars().all()
    out = []
    for a in accounts:
        resp = AccountResponse.model_validate(a)
        resp.group_name = a.group.name if a.group else None
        out.append(resp)
    return out


@router.post("", response_model=AccountResponse)
async def add_account(
    payload: AccountCreate, session: AsyncSession = Depends(get_session)
):
    from config import DEFAULT_CLIENT_ID

    # Check duplicate
    existing = await session.execute(
        select(Account).where(Account.email == payload.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"账号 {payload.email} 已存在")

    account = Account(
        email=payload.email,
        password=payload.password,
        client_id=payload.client_id or DEFAULT_CLIENT_ID,
        refresh_token=payload.refresh_token,
        group_id=payload.group_id,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    resp = AccountResponse.model_validate(account)
    resp.group_name = account.group.name if account.group else None
    return resp


@router.post("/batch", response_model=BatchImportResult)
async def batch_import(
    payload: BatchImportRequest, session: AsyncSession = Depends(get_session)
):
    lines = payload.text.strip().split("\n")
    total = 0
    success = 0
    failed = 0
    errors: List[str] = []

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        total += 1
        parts = line.split("----")
        if len(parts) not in (2, 4):
            failed += 1
            errors.append(f"第 {i} 行格式错误：需要2或4个字段，实际 {len(parts)} 个")
            continue

        email = parts[0].strip()
        password = parts[1].strip()
        client_id = parts[2].strip() if len(parts) > 2 else None
        refresh_token = parts[3].strip() if len(parts) > 3 else None

        if not email or not password:
            failed += 1
            errors.append(f"第 {i} 行邮箱和密码不能为空")
            continue

        # Skip duplicate
        existing = await session.execute(
            select(Account).where(Account.email == email)
        )
        if existing.scalar_one_or_none():
            failed += 1
            errors.append(f"第 {i} 行：{email} 已存在")
            continue

        account = Account(
            email=email,
            password=password,
            client_id=client_id or None,
            refresh_token=refresh_token or None,
            group_id=payload.group_id,
        )
        session.add(account)
        success += 1

    await session.commit()
    return BatchImportResult(total=total, success=success, failed=failed, errors=errors)


@router.delete("/{account_id}")
async def delete_account(
    account_id: int, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")
    await session.delete(account)
    await session.commit()
    return {"message": "已删除"}


@router.patch("/{account_id}/group")
async def update_account_group(
    account_id: int,
    payload: AccountUpdateGroup,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")
    account.group_id = payload.group_id
    await session.commit()
    return {"message": "分组已更新"}


@router.patch("/batch-group")
async def batch_update_group(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    """Batch move accounts to a group. payload: {account_ids: [int], group_id: int|null}"""
    account_ids = payload.get("account_ids", [])
    group_id = payload.get("group_id")
    if not account_ids:
        raise HTTPException(400, "请选择账号")

    result = await session.execute(
        select(Account).where(Account.id.in_(account_ids))
    )
    accounts = result.scalars().all()
    for a in accounts:
        a.group_id = group_id
    await session.commit()
    return {"message": f"已移动 {len(accounts)} 个账号"}


@router.post("/{account_id}/sync")
async def sync_account(
    account_id: int, session: AsyncSession = Depends(get_session)
):
    """Manually trigger sync for a single account."""
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    try:
        account.status = "syncing"
        await session.commit()

        # Refresh token
        token_data = await outlook_client.refresh_access_token(
            account.client_id, account.refresh_token
        )
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data["refresh_token"]
        account.token_expires_at = datetime.utcnow() + timedelta(
            seconds=token_data["expires_in"]
        )

        # Get unread count
        unread = await outlook_client.get_unread_count(account.access_token)
        account.unread_count = unread
        account.status = "active"
        account.last_synced = datetime.utcnow()
        account.last_error = None

        # Save emails to local DB
        from scheduler import _save_emails
        saved = await _save_emails(session, account, account.access_token)

        await session.commit()

        return {"message": "同步成功", "unread_count": unread, "emails_saved": saved}

    except Exception as e:
        account.status = "error"
        account.last_error = str(e)[:500]
        await session.commit()
        raise HTTPException(500, f"同步失败: {str(e)[:200]}")


@router.get("/export", response_class=PlainTextResponse)
async def export_accounts(
    group_id: int = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Export accounts as text file: email----password----client_id----refresh_token"""
    q = select(Account)
    if group_id is not None:
        q = q.where(Account.group_id == group_id)
    q = q.order_by(Account.created_at.asc())
    result = await session.execute(q)
    accounts = result.scalars().all()

    lines = []
    for a in accounts:
        line = f"{a.email}----{a.password}----{a.client_id or ''}----{a.refresh_token or ''}"
        lines.append(line)

    return PlainTextResponse(
        "\n".join(lines),
        headers={"Content-Disposition": "attachment; filename=accounts_export.txt"}
    )
