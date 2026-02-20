import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models import Setting
from schemas import SettingsUpdate, PasswordChange

logger = logging.getLogger("settings")

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(session: AsyncSession = Depends(get_session)):
    """Get all settings as a dict."""
    result = await session.execute(select(Setting))
    settings = result.scalars().all()
    return {s.key: s.value for s in settings}


@router.put("")
async def update_settings(
    payload: SettingsUpdate, session: AsyncSession = Depends(get_session)
):
    """Batch update settings."""
    for item in payload.settings:
        result = await session.execute(
            select(Setting).where(Setting.key == item.key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = item.value
            setting.updated_at = datetime.utcnow()
        else:
            setting = Setting(key=item.key, value=item.value)
            session.add(setting)
    await session.commit()
    return {"message": "设置已更新"}


@router.put("/password")
async def change_password(
    payload: PasswordChange, session: AsyncSession = Depends(get_session)
):
    """Change login password."""
    from config import AUTH_PASSWORD

    # Verify old password
    if payload.old_password != AUTH_PASSWORD:
        # Also check if password was stored in settings
        result = await session.execute(
            select(Setting).where(Setting.key == "auth_password")
        )
        setting = result.scalar_one_or_none()
        if setting:
            if payload.old_password != setting.value:
                raise HTTPException(400, "旧密码不正确")
        else:
            raise HTTPException(400, "旧密码不正确")

    if len(payload.new_password) < 4:
        raise HTTPException(400, "新密码至少需要4位")

    # Save new password to settings
    result = await session.execute(
        select(Setting).where(Setting.key == "auth_password")
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = payload.new_password
        setting.updated_at = datetime.utcnow()
    else:
        setting = Setting(key="auth_password", value=payload.new_password)
        session.add(setting)
    await session.commit()

    logger.info("Password changed successfully")
    return {"message": "密码已修改"}
