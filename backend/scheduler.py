import asyncio
import logging
from datetime import datetime, timedelta
from collections import deque
from dateutil import parser as dtparser
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from config import STAGGER_INTERVAL_MINUTES, ROUND_COOLDOWN_HOURS
from database import async_session
from models import Account, Group, Email
from outlook_client import outlook_client

from typing import Dict, List

logger = logging.getLogger("scheduler")

# Store new-email events: {account_id: new_unread_count}
new_email_events: Dict[int, int] = {}

# Track which single account to sync next (round-robin)
_next_account_offset: int = 0

# Track current round number
_current_round: int = 1

# Whether we are in cooldown (paused between rounds)
_in_cooldown: bool = False
_cooldown_until: datetime = None

# Sync log: store recent sync entries (max 200)
MAX_LOG_ENTRIES = 200
sync_log: deque = deque(maxlen=MAX_LOG_ENTRIES)

scheduler = AsyncIOScheduler()


def _add_log(level: str, email: str, message: str):
    """Add an entry to the sync log."""
    sync_log.appendleft({
        "time": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "email": email,
        "message": message,
    })


async def _save_emails(session, account: Account, access_token: str):
    """Fetch latest emails from Graph API and save new ones to local DB."""
    try:
        data = await outlook_client.fetch_emails(access_token, top=30)
        messages = data.get("value", [])
        if not messages:
            return 0

        # Get existing message_ids for this account
        existing_result = await session.execute(
            select(Email.message_id).where(Email.account_id == account.id)
        )
        existing_ids = set(r[0] for r in existing_result.all())

        new_count = 0
        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id or msg_id in existing_ids:
                continue

            # Parse sender
            sender_name = None
            sender_address = None
            fr = msg.get("from")
            if fr and fr.get("emailAddress"):
                ea = fr["emailAddress"]
                sender_name = ea.get("name")
                sender_address = ea.get("address")

            # Parse received time
            received_at = None
            raw_time = msg.get("receivedDateTime")
            if raw_time:
                try:
                    received_at = dtparser.isoparse(raw_time).replace(tzinfo=None)
                except Exception:
                    pass

            email_record = Email(
                account_id=account.id,
                message_id=msg_id,
                subject=(msg.get("subject") or "")[:500],
                sender_name=(sender_name or "")[:255],
                sender_address=(sender_address or "")[:255],
                is_read=msg.get("isRead", False),
                body_preview=(msg.get("bodyPreview") or "")[:500],
                received_at=received_at,
            )
            session.add(email_record)
            new_count += 1

        return new_count
    except Exception as e:
        logger.warning(f"保存邮件失败 {account.email}: {e}")
        return 0


async def sync_one_account():
    """Background job: sync ONE account from auto_sync-enabled groups (staggered).
    After completing a full round, pause for ROUND_COOLDOWN_HOURS.
    """
    global _next_account_offset, _current_round, _in_cooldown, _cooldown_until

    # Check if we are in cooldown
    if _in_cooldown:
        if datetime.utcnow() < _cooldown_until:
            remaining = (_cooldown_until - datetime.utcnow()).total_seconds() / 60
            logger.info(f"⏸ 冷却中，还需等待 {remaining:.0f} 分钟后开始第 {_current_round} 轮")
            return
        else:
            # Cooldown finished
            _in_cooldown = False
            _cooldown_until = None
            _add_log("info", "-", f"第 {_current_round} 轮同步开始")
            logger.info(f"✅ 冷却结束，开始第 {_current_round} 轮同步")

    async with async_session() as session:
        # Get groups with auto_sync enabled
        group_result = await session.execute(
            select(Group.id).where(Group.auto_sync == True)
        )
        auto_sync_group_ids = [r[0] for r in group_result.all()]

        if not auto_sync_group_ids:
            logger.info("没有启用自动同步的分组，跳过")
            _add_log("info", "-", "没有启用自动同步的分组，跳过")
            return

        # Only sync accounts belonging to auto_sync groups
        result = await session.execute(
            select(Account)
            .where(
                Account.status != "disabled",
                Account.group_id.in_(auto_sync_group_ids),
            )
            .order_by(Account.id)
        )
        all_accounts: List[Account] = list(result.scalars().all())
        total = len(all_accounts)

        if total == 0:
            logger.info("自动同步的分组中没有账号")
            _add_log("info", "-", "自动同步的分组中没有账号")
            return

        # Pick ONE account (round-robin)
        idx = _next_account_offset % total
        account = all_accounts[idx]

        logger.info(
            f"⏱ 第{_current_round}轮 错峰同步: 第 {idx + 1}/{total} 个账号 — {account.email}"
        )

        try:
            token_data = await outlook_client.refresh_access_token(
                account.client_id, account.refresh_token
            )
            account.access_token = token_data["access_token"]
            account.refresh_token = token_data["refresh_token"]
            account.token_expires_at = datetime.utcnow() + timedelta(
                seconds=token_data["expires_in"]
            )

            unread = await outlook_client.get_unread_count(account.access_token)
            old_unread = account.unread_count or 0

            if unread > old_unread:
                new_email_events[account.id] = unread - old_unread
                _add_log("info", account.email, f"{unread - old_unread} 封新邮件")
                logger.info(
                    f"📬 {account.email}: {unread - old_unread} 封新邮件"
                )

            account.unread_count = unread
            account.status = "active"
            account.last_synced = datetime.utcnow()
            account.last_error = None

            # Save emails to local DB
            saved = await _save_emails(session, account, account.access_token)
            if saved > 0:
                _add_log("info", account.email, f"保存了 {saved} 封新邮件到本地")
                logger.info(f"💾 {account.email}: 保存了 {saved} 封新邮件到本地")

            _add_log("success", account.email, f"同步成功 ({idx + 1}/{total})，未读: {unread}")

        except Exception as e:
            err_msg = str(e)[:200]
            logger.error(f"同步 {account.email} 失败: {e}")
            account.status = "error"
            account.last_error = str(e)[:500]
            _add_log("error", account.email, f"同步失败: {err_msg}")

        await session.commit()

        # Advance offset
        next_idx = (idx + 1) % total
        _next_account_offset = next_idx

        # Check if we just finished a full round
        if next_idx == 0:
            _current_round += 1
            _in_cooldown = True
            _cooldown_until = datetime.utcnow() + timedelta(hours=ROUND_COOLDOWN_HOURS)
            _add_log("info", "-",
                     f"本轮同步完成（共 {total} 个账号），冷却 {ROUND_COOLDOWN_HOURS} 小时后开始第 {_current_round} 轮")
            logger.info(
                f"🏁 本轮同步完成（共 {total} 个账号），"
                f"冷却 {ROUND_COOLDOWN_HOURS} 小时后开始第 {_current_round} 轮"
            )

    logger.info("本次同步完成")


def get_sync_status():
    """Return current sync scheduler status for the API."""
    job = scheduler.get_job("sync_staggered")
    running = job is not None
    return {
        "running": running,
        "interval_minutes": STAGGER_INTERVAL_MINUTES,
        "cooldown_hours": ROUND_COOLDOWN_HOURS,
        "current_round": _current_round,
        "in_cooldown": _in_cooldown,
        "cooldown_until": _cooldown_until.isoformat() + "Z" if _cooldown_until else None,
        "next_offset": _next_account_offset,
        "next_run": str(job.next_run_time) if job else None,
    }


def get_sync_log():
    """Return recent sync log entries."""
    return list(sync_log)


def start_scheduler():
    scheduler.add_job(
        sync_one_account,
        "interval",
        minutes=STAGGER_INTERVAL_MINUTES,
        id="sync_staggered",
        replace_existing=True,
    )
    scheduler.start()
    _add_log("info", "-", f"调度器启动: 每 {STAGGER_INTERVAL_MINUTES} 分钟同步 1 个账号，每轮冷却 {ROUND_COOLDOWN_HOURS} 小时")
    logger.info(
        f"调度器已启动，每 {STAGGER_INTERVAL_MINUTES} 分钟同步 1 个账号，"
        f"每轮完成后冷却 {ROUND_COOLDOWN_HOURS} 小时"
    )


def stop_scheduler():
    scheduler.shutdown(wait=False)
