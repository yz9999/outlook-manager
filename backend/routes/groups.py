from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

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
    if payload.proxy_url is not None:
        group.proxy_url = payload.proxy_url
    if payload.auto_sync is not None:
        group.auto_sync = payload.auto_sync

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
