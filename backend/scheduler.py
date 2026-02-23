import asyncio
import logging
from datetime import datetime, timedelta
from collections import deque
from dateutil import parser as dtparser
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import async_session
from models import Account, Group, Email
from outlook_client import outlook_client

from typing import Dict, List

logger = logging.getLogger("scheduler")

# Store new-email events: {account_id: new_unread_count}
new_email_events: Dict[int, int] = {}

# Track per-group round-robin state: {group_id: offset}
_group_offsets: Dict[int, int] = {}

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


async def _maybe_refresh_token(account: Account, proxy_url: str = None):
    """Refresh token only if expired or expiring within 5 minutes.
    Returns True if token was refreshed (or still valid), False on error.
    """
    now = datetime.utcnow()
    # If token_expires_at is set and not expiring within 5 min, skip refresh
    if account.token_expires_at and account.token_expires_at > now + timedelta(minutes=5):
        return True

    # Token expired or about to expire — refresh
    try:
        token_data = await outlook_client.refresh_access_token(
            account.client_id, account.refresh_token, proxy_url=proxy_url
        )
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data["refresh_token"]
        account.token_expires_at = now + timedelta(seconds=token_data["expires_in"])
        logger.info(f"🔑 Token 已刷新: {account.email}")
        return True
    except Exception as e:
        logger.warning(f"🔑 Token 刷新失败 {account.email}: {e}")
        return False


async def _save_emails_from_list(session, account: Account, messages: list):
    """Save pre-parsed messages (from IMAP/POP3) to local DB.
    Messages use the same Graph-API-like format from outlook_client.
    """
    try:
        if not messages:
            return 0

        existing_result = await session.execute(
            select(Email.message_id).where(Email.account_id == account.id)
        )
        existing_ids = set(r[0] for r in existing_result.all())

        new_count = 0
        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id or msg_id in existing_ids:
                continue

            sender_name = None
            sender_address = None
            fr = msg.get("from")
            if fr and fr.get("emailAddress"):
                ea = fr["emailAddress"]
                sender_name = ea.get("name")
                sender_address = ea.get("address")

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


async def _sync_accounts_for_group(group_id: int):
    """Background job: sync batch of accounts from a specific group (round-robin)."""
    global _group_offsets

    async with async_session() as session:
        # Load group config
        grp_result = await session.execute(
            select(Group).where(Group.id == group_id)
        )
        grp = grp_result.scalar_one_or_none()
        if not grp or not grp.auto_sync:
            return

        batch_size = grp.sync_batch_size or 1
        proxy_url = grp.proxy_url or None

        # Get accounts in this group
        result = await session.execute(
            select(Account)
            .where(
                Account.status != "disabled",
                Account.group_id == group_id,
            )
            .order_by(Account.id)
        )
        all_accounts: List[Account] = list(result.scalars().all())
        total = len(all_accounts)

        if total == 0:
            return

        # Pick batch_size accounts (round-robin)
        offset = _group_offsets.get(group_id, 0) % total
        batch_indices = []
        for i in range(batch_size):
            idx = (offset + i) % total
            batch_indices.append(idx)
            if idx == total - 1 and i < batch_size - 1:
                # Wrap around but still continue batch
                pass

        # De-duplicate indices (in case batch_size > total)
        seen = set()
        unique_indices = []
        for idx in batch_indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append(idx)

        for idx in unique_indices:
            account = all_accounts[idx]
            logger.info(
                f"⏱ 分组[{grp.name}] 同步: 第 {idx + 1}/{total} 个账号 — {account.email}"
            )

            try:
                # Only refresh token if expired/expiring
                token_ok = await _maybe_refresh_token(account, proxy_url)
                if not token_ok:
                    _add_log("error", account.email, "Token 过期且刷新失败，跳过同步")
                    account.status = "error"
                    account.last_error = "Token 过期且刷新失败"
                    await session.commit()
                    continue

                used_method = None
                saved = 0
                sync_errors = []

                # Fallback chain: Graph → IMAP New → IMAP Old
                methods_order = ["graph", "imap_new", "imap_old"]
                if account.sync_method and account.sync_method in methods_order:
                    methods_order.remove(account.sync_method)
                    methods_order.insert(0, account.sync_method)

                for method in methods_order:
                    try:
                        if method == "graph":
                            data = await outlook_client.fetch_emails(
                                account.access_token, top=30, proxy_url=proxy_url
                            )
                            unread = await outlook_client.get_unread_count(account.access_token, proxy_url=proxy_url)
                            old_unread = account.unread_count or 0
                            if unread > old_unread:
                                new_email_events[account.id] = unread - old_unread
                                _add_log("info", account.email, f"{unread - old_unread} 封新邮件")
                                logger.info(f"📬 {account.email}: {unread - old_unread} 封新邮件")
                            account.unread_count = unread
                            account.graph_enabled = True
                            saved = await _save_emails_from_list(session, account, data.get("value", []))
                            used_method = "graph"

                        elif method in ("imap_new", "imap_old"):
                            data = await outlook_client.fetch_emails_imap(
                                account.email, account.password,
                                account.client_id, account.refresh_token,
                                top=30, method=method,
                            )
                            imap_unread = data.get("_unread_count", 0)
                            old_unread = account.unread_count or 0
                            if imap_unread > old_unread:
                                new_email_events[account.id] = imap_unread - old_unread
                                _add_log("info", account.email, f"{imap_unread - old_unread} 封新邮件")
                                logger.info(f"📬 {account.email}: {imap_unread - old_unread} 封新邮件 (IMAP)")
                            account.unread_count = imap_unread
                            account.imap_enabled = True
                            saved = await _save_emails_from_list(session, account, data.get("value", []))
                            used_method = method

                        # Success — mark and break
                        account.sync_method = used_method
                        break
                    except Exception as e:
                        sync_errors.append(f"{method}: {str(e)[:100]}")
                        logger.info(f"{method} 失败 {account.email}: {e}")

                if not used_method:
                    account.sync_method = None
                    account.graph_enabled = None  # 重置，下次重新尝试 Graph
                    raise Exception("所有协议均失败: " + "; ".join(sync_errors))

                account.status = "active"
                account.last_synced = datetime.utcnow()
                account.last_error = None

                if saved > 0:
                    _add_log("info", account.email, f"保存了 {saved} 封新邮件到本地")
                    logger.info(f"💾 {account.email}: 保存了 {saved} 封新邮件到本地")

                method_labels = {"graph": "Graph", "imap_new": "IMAP(新)", "imap_old": "IMAP(旧)"}
                _add_log("success", account.email,
                         f"同步成功 via {method_labels.get(used_method, used_method)} ({idx + 1}/{total})，未读: {account.unread_count}")

            except Exception as e:
                err_msg = str(e)[:200]
                logger.error(f"同步 {account.email} 失败: {e}")
                account.status = "error"
                account.last_error = str(e)[:500]
                _add_log("error", account.email, f"同步失败: {err_msg}")

        await session.commit()

        # Advance offset
        next_offset = (offset + len(unique_indices)) % total
        _group_offsets[group_id] = next_offset

    logger.info(f"分组[{group_id}] 本次同步完成")


async def _refresh_group_tokens(group_id: int):
    """Scheduled job: refresh tokens for all accounts in a specific group."""
    async with async_session() as session:
        grp_result = await session.execute(
            select(Group).where(Group.id == group_id)
        )
        grp = grp_result.scalar_one_or_none()
        if not grp:
            return

        proxy_url = grp.proxy_url or None

        result = await session.execute(
            select(Account).where(
                Account.group_id == group_id,
                Account.refresh_token.isnot(None),
            )
        )
        accounts = list(result.scalars().all())

        if not accounts:
            return

        logger.info(f"⏰ 分组[{grp.name}] 定时刷新 Token 开始 ({len(accounts)} 个账号)")
        _add_log("info", "-", f"分组[{grp.name}] 定时刷新 Token 开始")

        from routes.refresh import _do_refresh_one
        success_count = 0
        fail_count = 0

        for account in accounts:
            ok, err = await _do_refresh_one(account, session, refresh_type="auto")
            if ok:
                success_count += 1
            else:
                fail_count += 1

        _add_log("info", "-",
                 f"分组[{grp.name}] Token 刷新完成: 成功 {success_count}, 失败 {fail_count}")
        logger.info(f"⏰ 分组[{grp.name}] Token 刷新完成: 成功 {success_count}, 失败 {fail_count}")


def get_sync_status():
    """Return current sync scheduler status for the API."""
    jobs = scheduler.get_jobs()
    sync_jobs = [j for j in jobs if j.id.startswith("sync_group_")]
    refresh_jobs = [j for j in jobs if j.id.startswith("refresh_group_")]
    return {
        "running": len(sync_jobs) > 0,
        "sync_groups": len(sync_jobs),
        "refresh_groups": len(refresh_jobs),
        "group_offsets": dict(_group_offsets),
        "jobs": [
            {
                "id": j.id,
                "next_run": str(j.next_run_time) if j.next_run_time else None,
            }
            for j in jobs
        ],
    }


def get_sync_log():
    """Return recent sync log entries."""
    return list(sync_log)


async def auto_refresh_all_tokens():
    """Scheduled job: refresh all account tokens."""
    logger.info("⏰ 定时刷新 Token 开始")
    _add_log("info", "-", "定时刷新 Token 开始")

    from routes.refresh import _do_refresh_one

    async with async_session() as session:
        result = await session.execute(
            select(Account).where(Account.refresh_token.isnot(None))
        )
        accounts = list(result.scalars().all())
        success_count = 0
        fail_count = 0

        for account in accounts:
            ok, err = await _do_refresh_one(account, session, refresh_type="auto")
            if ok:
                success_count += 1
            else:
                fail_count += 1

        _add_log("info", "-",
                 f"定时刷新完成: 成功 {success_count}, 失败 {fail_count}")
        logger.info(f"⏰ 定时刷新完成: 成功 {success_count}, 失败 {fail_count}")


async def init_refresh_schedule():
    """Load timed refresh config from settings DB and schedule if enabled."""
    try:
        from models import Setting
        async with async_session() as session:
            # Check if refresh is enabled
            result = await session.execute(
                select(Setting).where(Setting.key == "refresh_enabled")
            )
            enabled_setting = result.scalar_one_or_none()
            if not enabled_setting or enabled_setting.value != "true":
                logger.info("定时刷新未启用")
                return

            # Get refresh mode
            result = await session.execute(
                select(Setting).where(Setting.key == "refresh_mode")
            )
            mode_setting = result.scalar_one_or_none()
            mode = mode_setting.value if mode_setting else "days"

            if mode == "cron":
                result = await session.execute(
                    select(Setting).where(Setting.key == "refresh_cron")
                )
                cron_setting = result.scalar_one_or_none()
                if cron_setting and cron_setting.value:
                    from croniter import croniter
                    parts = cron_setting.value.strip().split()
                    if len(parts) == 5:
                        scheduler.add_job(
                            auto_refresh_all_tokens,
                            "cron",
                            minute=parts[0],
                            hour=parts[1],
                            day=parts[2],
                            month=parts[3],
                            day_of_week=parts[4],
                            id="token_refresh",
                            replace_existing=True,
                        )
                        logger.info(f"定时刷新已配置 (cron: {cron_setting.value})")
                        _add_log("info", "-", f"定时刷新已配置 (cron: {cron_setting.value})")
                    return
            else:
                result = await session.execute(
                    select(Setting).where(Setting.key == "refresh_days")
                )
                days_setting = result.scalar_one_or_none()
                days = int(days_setting.value) if days_setting and days_setting.value else 30
                scheduler.add_job(
                    auto_refresh_all_tokens,
                    "interval",
                    days=days,
                    id="token_refresh",
                    replace_existing=True,
                )
                logger.info(f"定时刷新已配置 (每 {days} 天)")
                _add_log("info", "-", f"定时刷新已配置 (每 {days} 天)")

    except Exception as e:
        logger.warning(f"加载定时刷新配置失败: {e}")


async def _setup_group_jobs():
    """Set up per-group sync and refresh jobs based on group settings."""
    async with async_session() as session:
        result = await session.execute(
            select(Group).where(Group.auto_sync == True)
        )
        groups = list(result.scalars().all())

        for grp in groups:
            # Add sync job for this group
            interval_min = grp.sync_interval_minutes or 2
            job_id = f"sync_group_{grp.id}"
            scheduler.add_job(
                _sync_accounts_for_group,
                "interval",
                minutes=interval_min,
                args=[grp.id],
                id=job_id,
                replace_existing=True,
            )
            logger.info(
                f"📅 分组[{grp.name}] 同步已配置: 每 {interval_min} 分钟, "
                f"每批 {grp.sync_batch_size or 1} 个账号"
            )
            _add_log("info", "-",
                     f"分组[{grp.name}] 同步: 每 {interval_min} 分钟, 每批 {grp.sync_batch_size or 1} 个")

            # Add token refresh job if enabled
            if grp.auto_refresh_token:
                refresh_hours = grp.refresh_interval_hours or 24
                refresh_job_id = f"refresh_group_{grp.id}"
                scheduler.add_job(
                    _refresh_group_tokens,
                    "interval",
                    hours=refresh_hours,
                    args=[grp.id],
                    id=refresh_job_id,
                    replace_existing=True,
                )
                logger.info(f"📅 分组[{grp.name}] Token 刷新: 每 {refresh_hours} 小时")
                _add_log("info", "-", f"分组[{grp.name}] Token 刷新: 每 {refresh_hours} 小时")


def start_scheduler():
    scheduler.start()
    _add_log("info", "-", "调度器启动")
    logger.info("调度器已启动")

    # Set up per-group jobs and timed refresh
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(_setup_group_jobs())
    loop.create_task(init_refresh_schedule())


def stop_scheduler():
    scheduler.shutdown(wait=False)
