import httpx
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from config import MS_TOKEN_URL, MS_GRAPH_BASE


class OutlookClient:
    """Wrapper for Microsoft Graph API to read Outlook emails."""

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._http.aclose()

    # ── Token Management ─────────────────────────────────

    async def refresh_access_token(
        self, client_id: str, refresh_token: str
    ) -> dict:
        """Exchange refresh_token for a new access_token.

        Returns dict with keys: access_token, refresh_token, expires_in
        """
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

    async def start_device_code_flow(self, client_id: str) -> dict:
        """Start device code flow. Returns device_code, user_code, verification_uri, interval, expires_in."""
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
        """Poll for token after user completes device code auth.
        Returns dict with access_token, refresh_token, expires_in.
        Raises Exception with 'authorization_pending' if user hasn't completed yet.
        """
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

    # ── Email Operations ─────────────────────────────────

    def _headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}

    async def fetch_emails(
        self,
        access_token: str,
        top: int = 30,
        skip: int = 0,
        folder: str = "inbox",
    ) -> Dict[str, Any]:
        """Fetch email list from a mail folder.

        Returns { 'value': [...], '@odata.count': int }
        """
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
        """Fetch a single email with full body."""
        url = (
            f"{MS_GRAPH_BASE}/me/messages/{message_id}"
            f"?$select=id,subject,from,toRecipients,receivedDateTime,"
            f"isRead,body,hasAttachments"
        )
        resp = await self._http.get(url, headers=self._headers(access_token))
        resp.raise_for_status()
        return resp.json()

    async def get_unread_count(self, access_token: str) -> int:
        """Get unread email count in inbox."""
        url = f"{MS_GRAPH_BASE}/me/mailFolders/inbox"
        resp = await self._http.get(url, headers=self._headers(access_token))
        resp.raise_for_status()
        data = resp.json()
        return data.get("unreadItemCount", 0)


# Singleton
outlook_client = OutlookClient()
