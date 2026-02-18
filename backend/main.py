import logging
import hashlib
import hmac
import json
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os

from database import init_db
from routes.accounts import router as accounts_router
from routes.emails import router as emails_router
from routes.groups import router as groups_router
from scheduler import start_scheduler, stop_scheduler, new_email_events, get_sync_status, get_sync_log
from config import AUTH_USERNAME, AUTH_PASSWORD, AUTH_SECRET

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

    # Skip auth for non-API routes (static files, SPA), login endpoint, and OPTIONS
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

    if username == AUTH_USERNAME and password == AUTH_PASSWORD:
        token = _make_token(username)
        return {"token": token, "username": username}

    return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})


# Routes
app.include_router(groups_router)
app.include_router(accounts_router)
app.include_router(emails_router)


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
