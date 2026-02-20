import logging
import json
import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from database import get_session, async_session
from models import Account, RefreshLog, Group, Setting
from schemas import RefreshLogResponse, RefreshStatsResponse
from outlook_client import outlook_client
from config import DEFAULT_CLIENT_ID

logger = logging.getLogger("refresh")

router = APIRouter(prefix="/api/accounts", tags=["refresh"])


async def _do_refresh_one(account, session, refresh_type="manual"):
    """Refresh token for a single account, returns (success, error_message)."""
    client_id = account.client_id or DEFAULT_CLIENT_ID
    if not client_id or not account.refresh_token:
        return False, "缺少 client_id 或 refresh_token"

    # Get proxy_url from group if available
    proxy_url = None
    if account.group_id:
        grp_result = await session.execute(
            select(Group).where(Group.id == account.group_id)
        )
        grp = grp_result.scalar_one_or_none()
        if grp and grp.proxy_url:
            proxy_url = grp.proxy_url

    try:
        token_data = await outlook_client.refresh_access_token(
            client_id, account.refresh_token, proxy_url=proxy_url
        )
        account.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            account.refresh_token = token_data["refresh_token"]
        account.token_expires_at = datetime.utcnow() + timedelta(
            seconds=token_data.get("expires_in", 3600)
        )
        account.last_refresh_at = datetime.utcnow()
        account.refresh_status = "success"
        account.status = "active"
        account.last_error = None

        # Log success
        log = RefreshLog(
            account_id=account.id,
            account_email=account.email,
            refresh_type=refresh_type,
            status="success",
        )
        session.add(log)
        await session.commit()
        return True, None
    except Exception as e:
        error_msg = str(e)
        account.refresh_status = "failed"
        account.last_error = error_msg

        # Log failure
        log = RefreshLog(
            account_id=account.id,
            account_email=account.email,
            refresh_type=refresh_type,
            status="failed",
            error_message=error_msg,
        )
        session.add(log)
        await session.commit()
        return False, error_msg


@router.get("/refresh-all")
async def refresh_all():
    """SSE stream: refresh all accounts one by one."""
    async def event_generator():
        async with async_session() as session:
            result = await session.execute(
                select(Account).where(Account.refresh_token.isnot(None))
            )
            accounts = list(result.scalars().all())
            total = len(accounts)
            success_count = 0
            fail_count = 0

            yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

            for i, account in enumerate(accounts):
                ok, err = await _do_refresh_one(account, session, refresh_type="manual")
                if ok:
                    success_count += 1
                else:
                    fail_count += 1

                yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total, 'email': account.email, 'success': ok, 'error': err, 'success_count': success_count, 'fail_count': fail_count}, ensure_ascii=False)}\n\n"

                await asyncio.sleep(0.1)  # Small delay between accounts

            yield f"data: {json.dumps({'type': 'done', 'total': total, 'success_count': success_count, 'fail_count': fail_count})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/refresh-stats", response_model=RefreshStatsResponse)
async def refresh_stats(session: AsyncSession = Depends(get_session)):
    """Get refresh statistics."""
    total = (await session.execute(
        select(func.count(Account.id)).where(Account.refresh_token.isnot(None))
    )).scalar() or 0

    success = (await session.execute(
        select(func.count(Account.id)).where(
            Account.refresh_token.isnot(None),
            Account.refresh_status == "success",
        )
    )).scalar() or 0

    failed = (await session.execute(
        select(func.count(Account.id)).where(
            Account.refresh_token.isnot(None),
            Account.refresh_status == "failed",
        )
    )).scalar() or 0

    return RefreshStatsResponse(
        total=total,
        success=success,
        failed=failed,
        unknown=total - success - failed,
    )


@router.get("/refresh-logs")
async def get_refresh_logs(
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Get refresh history (last 6 months)."""
    six_months_ago = datetime.utcnow() - timedelta(days=180)

    # Clean up old records
    await session.execute(
        delete(RefreshLog).where(RefreshLog.created_at < six_months_ago)
    )
    await session.commit()

    # Count total
    total = (await session.execute(
        select(func.count(RefreshLog.id)).where(
            RefreshLog.created_at >= six_months_ago
        )
    )).scalar() or 0

    # Fetch page
    result = await session.execute(
        select(RefreshLog)
        .where(RefreshLog.created_at >= six_months_ago)
        .order_by(RefreshLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return {
        "logs": [RefreshLogResponse.model_validate(log) for log in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/refresh-logs/failed")
async def get_failed_accounts(session: AsyncSession = Depends(get_session)):
    """Get accounts that are currently in failed refresh status."""
    result = await session.execute(
        select(Account).where(
            Account.refresh_token.isnot(None),
            Account.refresh_status == "failed",
        )
    )
    accounts = result.scalars().all()
    return [
        {
            "id": a.id,
            "email": a.email,
            "remark": a.remark,
            "last_error": a.last_error,
            "last_refresh_at": a.last_refresh_at.isoformat() if a.last_refresh_at else None,
            "group_id": a.group_id,
        }
        for a in accounts
    ]


@router.post("/{account_id}/retry-refresh")
async def retry_refresh_one(
    account_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Retry refresh for a single account."""
    result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账号不存在")

    ok, err = await _do_refresh_one(account, session, refresh_type="retry")
    if ok:
        return {"message": "刷新成功", "success": True}
    else:
        raise HTTPException(400, f"刷新失败: {err}")


@router.post("/refresh-failed")
async def retry_all_failed(session: AsyncSession = Depends(get_session)):
    """Retry refresh for all failed accounts."""
    result = await session.execute(
        select(Account).where(
            Account.refresh_token.isnot(None),
            Account.refresh_status == "failed",
        )
    )
    accounts = result.scalars().all()
    success_count = 0
    fail_count = 0

    for account in accounts:
        ok, _ = await _do_refresh_one(account, session, refresh_type="retry")
        if ok:
            success_count += 1
        else:
            fail_count += 1

    return {
        "message": f"重试完成: 成功 {success_count}, 失败 {fail_count}",
        "success_count": success_count,
        "fail_count": fail_count,
    }
