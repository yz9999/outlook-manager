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
            f"&$orderby=receivedDateTime asc"
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
