import logging
import hashlib
import hmac
import json
import time
import secrets
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os

from database import init_db, async_session
from sqlalchemy import select
from models import Account
from routes.accounts import router as accounts_router
from routes.emails import router as emails_router
from routes.groups import router as groups_router
from routes.settings import router as settings_router
from routes.refresh import router as refresh_router
from scheduler import start_scheduler, stop_scheduler, new_email_events, get_sync_status, get_sync_log
from config import AUTH_USERNAME, AUTH_PASSWORD, AUTH_SECRET, DEFAULT_CLIENT_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# ── Simple token helpers ──

def _make_token(username: str) -> str:
    """Create a simple HMAC-signed token: base64(payload).signature"""
    payload = json.dumps({"u": username, "t": int(time.time())})
    sig = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    import base64
    b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{b64}.{sig}"


def _verify_token(token: str) -> bool:
    """Verify a token is valid."""
    try:
        import base64
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        b64, sig = parts
        payload = base64.urlsafe_b64decode(b64).decode()
        expected = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False




@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    logger.info("数据库初始化完成")
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    from outlook_client import outlook_client
    await outlook_client.close()


app = FastAPI(title="Outlook 邮箱管理", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth middleware ──

# Paths that do NOT require auth
AUTH_WHITELIST = {"/api/auth/login"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Skip auth for non-API routes (static files, SPA), whitelisted endpoints, and OPTIONS
    if not path.startswith("/api/") or path in AUTH_WHITELIST or request.method == "OPTIONS":
        return await call_next(request)

    # Check Authorization header: "Bearer <token>"
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if _verify_token(token):
            return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "未授权，请先登录"})


# ── Auth routes ──

@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    # Check password from settings first, then env
    current_password = AUTH_PASSWORD
    try:
        from models import Setting
        async with async_session() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == "auth_password")
            )
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                current_password = setting.value
    except Exception:
        pass

    if username == AUTH_USERNAME and password == current_password:
        token = _make_token(username)
        return {"token": token, "username": username}

    return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})


# ── Device Code Flow ──

# Active device code sessions: {account_id: {device_code, interval, expires_at}}
_device_code_sessions: dict = {}


@app.post("/api/oauth/device-start/{account_id}")
async def device_code_start(account_id: int):
    """Start device code flow for an account."""
    from outlook_client import outlook_client

    try:
        result = await outlook_client.start_device_code_flow(DEFAULT_CLIENT_ID)
        _device_code_sessions[account_id] = {
            "device_code": result["device_code"],
            "interval": result.get("interval", 5),
            "expires_at": datetime.utcnow() + timedelta(seconds=result.get("expires_in", 900)),
        }
        return {
            "user_code": result["user_code"],
            "verification_uri": result.get("verification_uri", "https://microsoft.com/devicelogin"),
            "expires_in": result.get("expires_in", 900),
        }
    except Exception as e:
        raise HTTPException(500, f"启动设备码流程失败: {str(e)[:200]}")


@app.post("/api/oauth/device-poll/{account_id}")
async def device_code_poll(account_id: int):
    """Poll to check if user completed device code authorization."""
    from outlook_client import outlook_client

    session_data = _device_code_sessions.get(account_id)
    if not session_data:
        raise HTTPException(400, "没有进行中的授权流程，请重新开始")

    if datetime.utcnow() > session_data["expires_at"]:
        _device_code_sessions.pop(account_id, None)
        raise HTTPException(400, "授权已过期，请重新开始")

    try:
        token_data = await outlook_client.poll_device_code_token(
            DEFAULT_CLIENT_ID, session_data["device_code"]
        )
    except Exception as e:
        err_msg = str(e)
        if "authorization_pending" in err_msg or "slow_down" in err_msg:
            return {"status": "pending", "message": "等待用户完成授权..."}
        _device_code_sessions.pop(account_id, None)
        logger.error(f"Device code poll error for account {account_id}: {err_msg}")
        raise HTTPException(400, f"授权失败: {err_msg[:200]}")

    # Success — save tokens to account
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Account).where(Account.id == account_id)
            )
            account = result.scalar_one_or_none()
            if not account:
                raise HTTPException(404, "账号不存在")

            account.client_id = DEFAULT_CLIENT_ID
            account.access_token = token_data["access_token"]
            account.refresh_token = token_data["refresh_token"]
            account.token_expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
            account.status = "active"
            account.last_error = None
            await session.commit()
            logger.info(f"✅ Account {account_id} authorized successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save tokens for account {account_id}: {e}")
        raise HTTPException(500, f"保存token失败: {str(e)[:200]}")
    finally:
        _device_code_sessions.pop(account_id, None)

    return {"status": "success", "message": "授权成功"}


# Routes
app.include_router(groups_router)
app.include_router(accounts_router)
app.include_router(emails_router)
app.include_router(settings_router)
app.include_router(refresh_router)


@app.get("/api/notifications")
async def get_notifications():
    """Get new-email notifications since last check, then clear."""
    events = dict(new_email_events)
    new_email_events.clear()
    return {"new_emails": events}


@app.post("/api/accounts/sync-all")
async def sync_all_now():
    """Manually trigger sync for the next account in the staggered queue."""
    from scheduler import sync_one_account as _sync
    await _sync()
    return {"message": "同步完成"}


@app.get("/api/sync-status")
async def sync_status():
    """Return current staggered sync scheduler status."""
    return get_sync_status()


@app.get("/api/sync-log")
async def sync_log_endpoint():
    """Return recent sync log entries."""
    return get_sync_log()


# Serve frontend static files in production
FRONTEND_DIST = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "dist"
)
if os.path.isdir(FRONTEND_DIST):
    from fastapi.responses import FileResponse

    # Serve static assets (js, css, images, etc.)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    # SPA catch-all: any non-API route returns index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
