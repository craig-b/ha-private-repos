"""GitHub REST API client for Private Repos integration."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from aiohttp import ClientSession, ClientResponseError

from .const import ACCOUNT_TYPE_ORG

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubAuthError(Exception):
    """Raised on 401/403 from GitHub."""


class GitHubAPIError(Exception):
    """Raised on other GitHub API errors."""


class GitHubAPI:
    """GitHub REST API client."""

    def __init__(
        self,
        session: ClientSession,
        owner: str,
        pat: str,
        account_type: str,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._owner = owner
        self._pat = pat
        self._account_type = account_type
        self._headers = {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @property
    def owner(self) -> str:
        """Return the configured owner."""
        return self._owner

    async def _request(
        self, method: str, url: str, **kwargs: Any
    ) -> Any:
        """Make an authenticated request to GitHub API."""
        resp = await self._session.request(
            method, url, headers=self._headers, **kwargs
        )
        if resp.status in (401, 403):
            raise GitHubAuthError(f"GitHub auth failed: {resp.status}")
        if resp.status == 404:
            return None
        if resp.status >= 400:
            text = await resp.text()
            raise GitHubAPIError(f"GitHub API error {resp.status}: {text}")
        return resp

    async def _get_json(self, url: str) -> Any:
        """GET request returning parsed JSON."""
        resp = await self._request("GET", url)
        if resp is None:
            return None
        return await resp.json()

    async def list_repos(self, page: int = 1, per_page: int = 100) -> list[dict]:
        """List repos for the configured owner. Returns one page."""
        if self._account_type == ACCOUNT_TYPE_ORG:
            url = f"{API_BASE}/orgs/{self._owner}/repos"
        else:
            url = f"{API_BASE}/users/{self._owner}/repos"
        result = await self._get_json(f"{url}?per_page={per_page}&page={page}")
        return result if result else []

    async def list_all_repos(self) -> list[dict]:
        """List all repos (paginated)."""
        repos: list[dict] = []
        page = 1
        while True:
            batch = await self.list_repos(page=page)
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos

    async def get_directory_contents(
        self, repo: str, path: str
    ) -> list[dict] | None:
        """Get directory listing. Returns None if path doesn't exist."""
        url = f"{API_BASE}/repos/{self._owner}/{repo}/contents/{path}"
        return await self._get_json(url)

    async def get_file_contents(self, repo: str, path: str) -> str | None:
        """Get file contents (base64 decoded). Returns None if not found."""
        url = f"{API_BASE}/repos/{self._owner}/{repo}/contents/{path}"
        data = await self._get_json(url)
        if data is None or "content" not in data:
            return None
        return base64.b64decode(data["content"]).decode("utf-8")

    async def get_latest_release(self, repo: str) -> dict | None:
        """Get the latest non-draft release. Returns None if no releases."""
        url = f"{API_BASE}/repos/{self._owner}/{repo}/releases/latest"
        return await self._get_json(url)

    async def download_zipball(self, repo: str, ref: str) -> bytes:
        """Download a zipball for a given ref (tag or branch)."""
        url = f"{API_BASE}/repos/{self._owner}/{repo}/zipball/{ref}"
        resp = await self._request("GET", url)
        if resp is None:
            raise GitHubAPIError(f"Failed to download zipball for {repo}@{ref}")
        return await resp.read()
