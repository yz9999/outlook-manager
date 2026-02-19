import httpx
import asyncio
import imaplib
import poplib
import email
import base64
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional, List, Dict, Any

from config import MS_TOKEN_URL, MS_GRAPH_BASE

logger = logging.getLogger("outlook_client")

# Token endpoints (matching reference project)
TOKEN_URL_LIVE = "https://login.live.com/oauth20_token.srf"
TOKEN_URL_IMAP = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
TOKEN_URL_GRAPH = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# IMAP server configs
IMAP_SERVER_OLD = "outlook.office365.com"
IMAP_SERVER_NEW = "outlook.live.com"
IMAP_PORT = 993


def _decode_header_str(raw):
    """Decode RFC2047 encoded email header."""
    if not raw:
        return ""
    parts = decode_header(raw)
    result = []
    for data, charset in parts:
        if isinstance(data, bytes):
            result.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(data)
    return "".join(result)


class OutlookClient:
    """Wrapper for Microsoft Graph API + IMAP/POP3 to read Outlook emails."""

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._http.aclose()

    # ── Token Management ─────────────────────────────────

    async def refresh_access_token(
        self, client_id: str, refresh_token: str
    ) -> dict:
        """Exchange refresh_token for a new access_token (Graph API scope)."""
        data = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://graph.microsoft.com/.default offline_access",
        }
        resp = await self._http.post(MS_TOKEN_URL, data=data)
        resp.raise_for_status()
        payload = resp.json()
        return {
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token", refresh_token),
            "expires_in": payload.get("expires_in", 3600),
        }

    async def _get_imap_token_old(self, client_id: str, refresh_token: str) -> Optional[str]:
        """旧版：通过 login.live.com 获取 access_token（无需 scope）"""
        try:
            data = {
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
            resp = await self._http.post(TOKEN_URL_LIVE, data=data)
            if resp.status_code != 200:
                logger.info(f"旧版 IMAP token 失败: {resp.status_code} {resp.text[:200]}")
                return None
            token = resp.json().get("access_token")
            if token:
                logger.info(f"旧版 IMAP token 获取成功, 长度: {len(token)}")
            return token
        except Exception as e:
            logger.info(f"旧版 IMAP token 异常: {e}")
            return None

    async def _get_imap_token_new(self, client_id: str, refresh_token: str) -> Optional[str]:
        """新版：通过 consumers 端点 + IMAP scope 获取 access_token"""
        try:
            data = {
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
            }
            resp = await self._http.post(TOKEN_URL_IMAP, data=data)
            if resp.status_code != 200:
                logger.info(f"新版 IMAP token 失败: {resp.status_code} {resp.text[:200]}")
                return None
            token = resp.json().get("access_token")
            if token:
                logger.info(f"新版 IMAP token 获取成功, 长度: {len(token)}")
            return token
        except Exception as e:
            logger.info(f"新版 IMAP token 异常: {e}")
            return None

    async def start_device_code_flow(self, client_id: str) -> dict:
        """Start device code flow."""
        url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
        data = {
            "client_id": client_id,
            "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.ReadWrite offline_access User.Read",
        }
        resp = await self._http.post(url, data=data)
        if resp.status_code != 200:
            try:
                err = resp.json()
                raise Exception(err.get("error_description", resp.text[:300]))
            except Exception:
                raise
        return resp.json()

    async def poll_device_code_token(self, client_id: str, device_code: str) -> dict:
        """Poll for token after user completes device code auth."""
        data = {
            "client_id": client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        }
        resp = await self._http.post(MS_TOKEN_URL, data=data)
        payload = resp.json()

        if resp.status_code != 200:
            error = payload.get("error", "unknown")
            if error in ("authorization_pending", "slow_down"):
                raise Exception(error)
            desc = payload.get("error_description", "")
            first_line = desc.split("\r\n")[0] if "\r\n" in desc else desc[:200]
            raise Exception(f"{error}: {first_line}")

        return {
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
            "expires_in": payload.get("expires_in", 3600),
        }

    # ── Graph API Email Operations ───────────────────────

    def _headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}

    async def fetch_emails(
        self,
        access_token: str,
        top: int = 30,
        skip: int = 0,
        folder: str = "inbox",
    ) -> Dict[str, Any]:
        """Fetch email list via Graph API."""
        url = (
            f"{MS_GRAPH_BASE}/me/mailFolders/{folder}/messages"
            f"?$top={top}&$skip={skip}"
            f"&$select=id,subject,from,receivedDateTime,isRead,bodyPreview"
            f"&$orderby=receivedDateTime desc"
            f"&$count=true"
        )
        resp = await self._http.get(url, headers=self._headers(access_token))
        resp.raise_for_status()
        return resp.json()

    async def fetch_email_detail(
        self, access_token: str, message_id: str
    ) -> Dict[str, Any]:
        """Fetch a single email with full body via Graph API."""
        url = (
            f"{MS_GRAPH_BASE}/me/messages/{message_id}"
            f"?$select=id,subject,from,toRecipients,receivedDateTime,"
            f"isRead,body,hasAttachments"
        )
        resp = await self._http.get(url, headers=self._headers(access_token))
        resp.raise_for_status()
        return resp.json()

    async def get_unread_count(self, access_token: str) -> int:
        """Get unread email count via Graph API."""
        url = f"{MS_GRAPH_BASE}/me/mailFolders/inbox"
        resp = await self._http.get(url, headers=self._headers(access_token))
        resp.raise_for_status()
        data = resp.json()
        return data.get("unreadItemCount", 0)

    # ── IMAP Email Operations ─────────────────────────────

    def _build_xoauth2_string(self, user_email: str, access_token: str) -> str:
        return f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"

    async def fetch_emails_imap(
        self, user_email: str, password: str,
        client_id: str = None, refresh_token: str = None,
        top: int = 30
    ) -> Dict[str, Any]:
        """Fetch emails via IMAP. Tries new method first, then old method.
        Reference: https://github.com/xiaozhi349/outlookEmail
        """
        if not client_id or not refresh_token:
            raise Exception("缺少 client_id 或 refresh_token")

        # Try 新版 IMAP first (outlook.live.com + IMAP scope)
        token_new = await self._get_imap_token_new(client_id, refresh_token)
        if token_new:
            try:
                result = await asyncio.to_thread(
                    self._fetch_imap_emails, user_email, token_new,
                    IMAP_SERVER_NEW, top)
                logger.info(f"新版 IMAP 成功 for {user_email}")
                return result
            except Exception as e:
                logger.info(f"新版 IMAP 连接失败 for {user_email}: {e}")

        # Try 旧版 IMAP (outlook.office365.com + login.live.com token)
        token_old = await self._get_imap_token_old(client_id, refresh_token)
        if token_old:
            try:
                result = await asyncio.to_thread(
                    self._fetch_imap_emails, user_email, token_old,
                    IMAP_SERVER_OLD, top)
                logger.info(f"旧版 IMAP 成功 for {user_email}")
                return result
            except Exception as e:
                logger.info(f"旧版 IMAP 连接失败 for {user_email}: {e}")

        raise Exception("IMAP 新版和旧版均失败")

    def _fetch_imap_emails(self, user_email: str, access_token: str,
                           imap_server: str, top: int) -> Dict[str, Any]:
        """Synchronous IMAP fetch, matching reference project's approach."""
        connection = imaplib.IMAP4_SSL(imap_server, IMAP_PORT)
        try:
            # XOAUTH2 auth (reference: auth_string.encode('utf-8'))
            auth_string = self._build_xoauth2_string(user_email, access_token).encode("utf-8")
            connection.authenticate("XOAUTH2", lambda x: auth_string)

            # Select INBOX (reference uses '"INBOX"' for new server)
            if imap_server == IMAP_SERVER_NEW:
                connection.select('"INBOX"')
            else:
                connection.select("INBOX")

            # Search all
            status, messages = connection.search(None, "ALL")
            if status != "OK" or not messages or not messages[0]:
                return {"value": [], "@odata.count": 0, "_unread_count": 0}

            message_ids = messages[0].split()
            total = len(message_ids)

            # Get latest N, newest first
            recent_ids = message_ids[-top:][::-1]

            # Get unseen count
            unread_count = 0
            s2, d2 = connection.search(None, "UNSEEN")
            if s2 == "OK" and d2[0]:
                unread_count = len(d2[0].split())

            result_emails = []
            for msg_id in recent_ids:
                try:
                    status, msg_data = connection.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not msg_data or not msg_data[0]:
                        continue

                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    subject = _decode_header_str(msg.get("Subject", ""))
                    from_raw = msg.get("From", "")
                    from_name, from_addr = parseaddr(from_raw)
                    from_name = _decode_header_str(from_name) if from_name else ""
                    msg_id_str = msg.get("Message-ID",
                                         msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id))

                    received_at = None
                    date_str = msg.get("Date")
                    if date_str:
                        try:
                            received_at = parsedate_to_datetime(date_str).isoformat()
                        except Exception:
                            pass

                    # Get body preview
                    body_preview = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            ct = part.get_content_type()
                            if ct == "text/plain":
                                try:
                                    body_preview = part.get_payload(decode=True).decode(
                                        part.get_content_charset() or "utf-8", errors="replace")[:200]
                                except Exception:
                                    pass
                                break
                    else:
                        try:
                            body_preview = msg.get_payload(decode=True).decode(
                                msg.get_content_charset() or "utf-8", errors="replace")[:200]
                        except Exception:
                            pass

                    result_emails.append({
                        "id": msg_id_str,
                        "subject": subject[:500],
                        "from": {
                            "emailAddress": {
                                "name": from_name[:255],
                                "address": from_addr[:255],
                            }
                        },
                        "receivedDateTime": received_at,
                        "isRead": True,  # IMAP RFC822 doesn't include FLAGS
                        "bodyPreview": body_preview[:500],
                    })
                except Exception as e:
                    logger.debug(f"IMAP parse msg {msg_id}: {e}")
                    continue

            return {
                "value": result_emails,
                "@odata.count": total,
                "_unread_count": unread_count,
            }
        finally:
            try:
                connection.logout()
            except Exception:
                pass

    # ── Protocol Detection ────────────────────────────────

    async def check_imap(self, user_email: str, password: str,
                         client_id: str = None, refresh_token: str = None) -> bool:
        """Check if IMAP works. Tries new method then old method."""
        if not client_id or not refresh_token:
            return False

        # Try 新版 IMAP
        token_new = await self._get_imap_token_new(client_id, refresh_token)
        if token_new:
            ok = await asyncio.to_thread(
                self._check_imap_connection, user_email, token_new, IMAP_SERVER_NEW)
            if ok:
                return True

        # Try 旧版 IMAP
        token_old = await self._get_imap_token_old(client_id, refresh_token)
        if token_old:
            ok = await asyncio.to_thread(
                self._check_imap_connection, user_email, token_old, IMAP_SERVER_OLD)
            if ok:
                return True

        return False

    def _check_imap_connection(self, user_email: str, access_token: str, imap_server: str) -> bool:
        """Test IMAP connection with OAuth2 token."""
        try:
            connection = imaplib.IMAP4_SSL(imap_server, IMAP_PORT)
            auth_string = self._build_xoauth2_string(user_email, access_token).encode("utf-8")
            connection.authenticate("XOAUTH2", lambda x: auth_string)
            connection.logout()
            logger.info(f"IMAP check OK for {user_email} via {imap_server}")
            return True
        except Exception as e:
            logger.info(f"IMAP check failed for {user_email} via {imap_server}: {e}")
            return False

    async def check_pop3(self, user_email: str, password: str,
                         client_id: str = None, refresh_token: str = None) -> bool:
        """Check if POP3 works (basic check, POP3 is less common)."""
        # POP3 is rarely used, just return False for now
        return False

    async def check_graph(self, access_token: str) -> bool:
        """Check if Graph API is accessible with the given token."""
        try:
            resp = await self._http.get(
                f"{MS_GRAPH_BASE}/me",
                headers=self._headers(access_token),
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Graph API check error: {e}")
            return False


# Singleton
outlook_client = OutlookClient()
