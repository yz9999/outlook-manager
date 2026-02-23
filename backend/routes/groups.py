from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
import httpx
import time

from database import get_session
from models import Group, Account
from schemas import GroupCreate, GroupUpdate, GroupResponse

router = APIRouter(prefix="/api/groups", tags=["groups"])


def _build_response(g, count):
    return GroupResponse(
        id=g.id,
        name=g.name,
        description=g.description,
        color=g.color,
        proxy_url=g.proxy_url,
        auto_sync=g.auto_sync,
        sync_interval_minutes=g.sync_interval_minutes or 2,
        sync_batch_size=g.sync_batch_size or 1,
        auto_refresh_token=g.auto_refresh_token if g.auto_refresh_token is not None else True,
        refresh_interval_hours=g.refresh_interval_hours or 24,
        account_count=count,
        created_at=g.created_at,
    )


async def _account_count(session, group_id):
    r = await session.execute(
        select(func.count(Account.id)).where(Account.group_id == group_id)
    )
    return r.scalar() or 0


@router.get("", response_model=List[GroupResponse])
async def list_groups(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Group).order_by(Group.created_at.desc())
    )
    groups = result.scalars().all()
    out = []
    for g in groups:
        count = await _account_count(session, g.id)
        out.append(_build_response(g, count))
    return out


@router.post("", response_model=GroupResponse)
async def create_group(
    payload: GroupCreate, session: AsyncSession = Depends(get_session)
):
    existing = await session.execute(
        select(Group).where(Group.name == payload.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"分组 '{payload.name}' 已存在")

    group = Group(
        name=payload.name,
        description=payload.description,
        color=payload.color,
        proxy_url=payload.proxy_url,
        auto_sync=payload.auto_sync,
        sync_interval_minutes=payload.sync_interval_minutes,
        sync_batch_size=payload.sync_batch_size,
        auto_refresh_token=payload.auto_refresh_token,
        refresh_interval_hours=payload.refresh_interval_hours,
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return _build_response(group, 0)


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    payload: GroupUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Group).where(Group.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "分组不存在")

    if payload.name is not None:
        dup = await session.execute(
            select(Group).where(Group.name == payload.name, Group.id != group_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(400, f"分组名 '{payload.name}' 已被使用")
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description
    if payload.color is not None:
        group.color = payload.color
    # Use model_fields_set to detect if proxy_url was explicitly sent (including null to clear)
    if "proxy_url" in payload.model_fields_set:
        group.proxy_url = payload.proxy_url if payload.proxy_url else None
    if payload.auto_sync is not None:
        group.auto_sync = payload.auto_sync
    if payload.sync_interval_minutes is not None:
        group.sync_interval_minutes = payload.sync_interval_minutes
    if payload.sync_batch_size is not None:
        group.sync_batch_size = payload.sync_batch_size
    if payload.auto_refresh_token is not None:
        group.auto_refresh_token = payload.auto_refresh_token
    if payload.refresh_interval_hours is not None:
        group.refresh_interval_hours = payload.refresh_interval_hours

    await session.commit()
    await session.refresh(group)

    count = await _account_count(session, group.id)
    return _build_response(group, count)


@router.delete("/{group_id}")
async def delete_group(
    group_id: int, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Group).where(Group.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "分组不存在")

    acct_result = await session.execute(
        select(Account).where(Account.group_id == group_id)
    )
    for acct in acct_result.scalars().all():
        acct.group_id = None

    await session.delete(group)
    await session.commit()
    return {"message": "分组已删除"}


@router.post("/{group_id}/test-proxy")
async def test_proxy(
    group_id: int, session: AsyncSession = Depends(get_session)
):
    """Test if the group's proxy is reachable."""
    result = await session.execute(
        select(Group).where(Group.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "分组不存在")
    if not group.proxy_url:
        raise HTTPException(400, "该分组未设置代理")

    start = time.time()
    try:
        async with httpx.AsyncClient(
            timeout=10.0, proxy=group.proxy_url
        ) as client:
            resp = await client.get("https://graph.microsoft.com/v1.0/$metadata")
            latency = round((time.time() - start) * 1000)
            return {
                "ok": True,
                "status_code": resp.status_code,
                "latency_ms": latency,
                "message": f"代理连接成功 ({latency}ms)",
            }
    except Exception as e:
        latency = round((time.time() - start) * 1000)
        return {
            "ok": False,
            "latency_ms": latency,
            "message": f"代理连接失败: {e}",
        }
