from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta
from typing import List

from database import get_session
from models import Account, Group
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
        remark=payload.remark,
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
        if len(parts) not in (2, 4, 5):
            failed += 1
            errors.append(f"第 {i} 行格式错误：需要2、4或5个字段，实际 {len(parts)} 个")
            continue

        email_addr = parts[0].strip()
        password = parts[1].strip()
        client_id = parts[2].strip() if len(parts) > 2 else None
        refresh_token = parts[3].strip() if len(parts) > 3 else None
        remark = parts[4].strip() if len(parts) > 4 else None

        if not email_addr or not password:
            failed += 1
            errors.append(f"第 {i} 行邮箱和密码不能为空")
            continue

        # Skip duplicate
        existing = await session.execute(
            select(Account).where(Account.email == email_addr)
        )
        if existing.scalar_one_or_none():
            failed += 1
            errors.append(f"第 {i} 行：{email_addr} 已存在")
            continue

        account = Account(
            email=email_addr,
            password=password,
            client_id=client_id or None,
            refresh_token=refresh_token or None,
            group_id=payload.group_id,
            remark=remark,
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
    """Manually trigger sync — tries Graph → IMAP → POP3 fallback."""
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    # Get proxy_url from group
    proxy_url = None
    if account.group_id:
        grp_result = await session.execute(
            select(Group).where(Group.id == account.group_id)
        )
        grp = grp_result.scalar_one_or_none()
        if grp and grp.proxy_url:
            proxy_url = grp.proxy_url

    try:
        account.status = "syncing"
        await session.commit()

        used_protocol = None
        sync_error_details = []

        # ── Refresh token only when expired/expiring ──
        from scheduler import _maybe_refresh_token
        token_ok = await _maybe_refresh_token(account, proxy_url)
        if not token_ok:
            sync_error_details.append("Token 过期且刷新失败")

        # ── Sync with fallback: Graph → IMAP New → IMAP Old ──
        # If account has a preferred method, try it first
        methods_order = ["graph", "imap_new", "imap_old"]
        if account.sync_method and account.sync_method in methods_order:
            # Move preferred method to front
            methods_order.remove(account.sync_method)
            methods_order.insert(0, account.sync_method)

        for method in methods_order:
            try:
                if method == "graph":
                    data = await outlook_client.fetch_emails(
                        account.access_token, top=30, proxy_url=proxy_url
                    )
                    unread = await outlook_client.get_unread_count(account.access_token, proxy_url=proxy_url)
                    account.unread_count = unread
                    account.graph_enabled = True
                    from scheduler import _save_emails_from_list
                    saved = await _save_emails_from_list(session, account, data.get("value", []))
                    used_protocol = "graph"

                elif method == "imap_new":
                    data = await outlook_client.fetch_emails_imap(
                        account.email, account.password,
                        account.client_id, account.refresh_token,
                        top=30, method="imap_new"
                    )
                    account.unread_count = data.get("_unread_count", 0)
                    account.imap_enabled = True
                    from scheduler import _save_emails_from_list
                    saved = await _save_emails_from_list(session, account, data.get("value", []))
                    used_protocol = "imap_new"

                elif method == "imap_old":
                    data = await outlook_client.fetch_emails_imap(
                        account.email, account.password,
                        account.client_id, account.refresh_token,
                        top=30, method="imap_old"
                    )
                    account.unread_count = data.get("_unread_count", 0)
                    account.imap_enabled = True
                    from scheduler import _save_emails_from_list
                    saved = await _save_emails_from_list(session, account, data.get("value", []))
                    used_protocol = "imap_old"

                # Success — mark method and break
                account.sync_method = used_protocol
                break

            except Exception as e:
                sync_error_details.append(f"{method}: {str(e)[:150]}")

        if not used_protocol:
            account.sync_method = None
            account.graph_enabled = None  # 重置，下次重新尝试 Graph
            raise Exception("所有协议均失败: " + "; ".join(sync_error_details))

        # Detect remaining protocols (best-effort)
        try:
            if account.graph_enabled is None and account.access_token:
                account.graph_enabled = await outlook_client.check_graph(account.access_token, proxy_url=proxy_url)
        except Exception:
            pass

        account.status = "active"
        account.last_synced = datetime.utcnow()
        account.last_error = None
        await session.commit()

        method_labels = {"graph": "Graph API", "imap_new": "IMAP (新版)", "imap_old": "IMAP (旧版)"}
        return {
            "message": f"同步成功 (via {method_labels.get(used_protocol, used_protocol)})",
            "unread_count": account.unread_count,
            "emails_saved": saved,
            "protocol": used_protocol,
            "sync_method": account.sync_method,
            "imap_enabled": account.imap_enabled,
            "pop3_enabled": account.pop3_enabled,
            "graph_enabled": account.graph_enabled,
        }

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
        line = f"{a.email}----{a.password}----{a.client_id or ''}----{a.refresh_token or ''}----{a.remark or ''}"
        lines.append(line)

    return PlainTextResponse(
        "\n".join(lines),
        headers={"Content-Disposition": "attachment; filename=accounts_export.txt"}
    )


@router.post("/export-selected", response_class=PlainTextResponse)
async def export_selected_accounts(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    """Export selected accounts by IDs: email----password----client_id----refresh_token"""
    account_ids = payload.get("account_ids", [])
    if not account_ids:
        raise HTTPException(400, "请选择要导出的账号")

    result = await session.execute(
        select(Account).where(Account.id.in_(account_ids)).order_by(Account.created_at.asc())
    )
    accounts = result.scalars().all()

    lines = []
    for a in accounts:
        line = f"{a.email}----{a.password}----{a.client_id or ''}----{a.refresh_token or ''}----{a.remark or ''}"
        lines.append(line)

    return PlainTextResponse(
        "\n".join(lines),
        headers={"Content-Disposition": "attachment; filename=accounts_export.txt"}
    )


@router.post("/{account_id}/check-protocols")
async def check_protocols(
    account_id: int, session: AsyncSession = Depends(get_session)
):
    """Check IMAP/POP3/Graph availability for a single account."""
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    try:
        # Check Graph (needs refresh_token)
        access_token = None
        if account.refresh_token and account.client_id:
            try:
                token_data = await outlook_client.refresh_access_token(
                    account.client_id, account.refresh_token
                )
                access_token = token_data["access_token"]
                account.access_token = access_token
                account.refresh_token = token_data["refresh_token"]
                account.graph_enabled = await outlook_client.check_graph(access_token)
            except Exception:
                account.graph_enabled = False
        else:
            account.graph_enabled = False

        # Check IMAP/POP3
        account.imap_enabled = await outlook_client.check_imap(
            account.email, account.password, account.client_id, account.refresh_token)
        account.pop3_enabled = await outlook_client.check_pop3(
            account.email, account.password, account.client_id, account.refresh_token)

        await session.commit()

        return {
            "imap_enabled": account.imap_enabled,
            "pop3_enabled": account.pop3_enabled,
            "graph_enabled": account.graph_enabled,
        }
    except Exception as e:
        await session.commit()
        raise HTTPException(500, f"检测失败: {str(e)[:200]}")


@router.post("/batch-check-protocols")
async def batch_check_protocols(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    """Batch check IMAP/POP3/Graph for selected accounts."""
    account_ids = payload.get("account_ids", [])
    if not account_ids:
        raise HTTPException(400, "请选择账号")

    result = await session.execute(
        select(Account).where(Account.id.in_(account_ids))
    )
    accounts = result.scalars().all()

    results = []
    for account in accounts:
        item = {"id": account.id, "email": account.email}
        try:
            # Check Graph
            if account.refresh_token and account.client_id:
                try:
                    token_data = await outlook_client.refresh_access_token(
                        account.client_id, account.refresh_token
                    )
                    access_token = token_data["access_token"]
                    account.access_token = access_token
                    account.refresh_token = token_data["refresh_token"]
                    account.graph_enabled = await outlook_client.check_graph(access_token)
                except Exception:
                    account.graph_enabled = False
            else:
                account.graph_enabled = False

            # Check IMAP/POP3
            account.imap_enabled = await outlook_client.check_imap(
                account.email, account.password, account.client_id, account.refresh_token)
            account.pop3_enabled = await outlook_client.check_pop3(
                account.email, account.password, account.client_id, account.refresh_token)

            item["imap_enabled"] = account.imap_enabled
            item["pop3_enabled"] = account.pop3_enabled
            item["graph_enabled"] = account.graph_enabled
        except Exception as e:
            item["error"] = str(e)[:200]

        results.append(item)

    await session.commit()
    return {"results": results}
