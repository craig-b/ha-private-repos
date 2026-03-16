"""DataUpdateCoordinator for Private Repos integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import json
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .github_api import GitHubAPI, GitHubAuthError, GitHubAPIError

_LOGGER = logging.getLogger(__name__)

SEMAPHORE_LIMIT = 5


@dataclass
class RepoIntegrationData:
    """Data about a discovered integration in a repo."""

    repo_full_name: str
    domain: str
    name: str
    latest_version: str | None
    release_url: str | None
    release_notes: str | None
    download_ref: str
    manifest: dict


class PrivateReposCoordinator(
    DataUpdateCoordinator[dict[str, RepoIntegrationData]]
):
    """Coordinator for polling GitHub and discovering integrations."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: GitHubAPI,
        store: Store,
        scan_interval_minutes: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Private Repos",
            config_entry=config_entry,
            update_interval=timedelta(minutes=scan_interval_minutes),
        )
        self.api = api
        self.store = store
        self.installed: dict[str, dict[str, Any]] = {}
        self._install_locks: dict[str, asyncio.Lock] = {}

    def get_install_lock(self, domain: str) -> asyncio.Lock:
        """Get or create a lock for a domain install."""
        if domain not in self._install_locks:
            self._install_locks[domain] = asyncio.Lock()
        return self._install_locks[domain]

    async def _async_setup(self) -> None:
        """Load installed integrations from store."""
        stored = await self.store.async_load()
        if stored and "integrations" in stored:
            self.installed = stored["integrations"]

    async def async_save_installed(self) -> None:
        """Persist installed integrations to store."""
        await self.store.async_save({"integrations": self.installed})

    async def _async_update_data(self) -> dict[str, RepoIntegrationData]:
        """Fetch data from GitHub."""
        try:
            repos = await self.api.list_all_repos()
        except GitHubAuthError as err:
            raise ConfigEntryAuthFailed from err
        except GitHubAPIError as err:
            raise UpdateFailed(f"Error listing repos: {err}") from err

        sem = asyncio.Semaphore(SEMAPHORE_LIMIT)
        tasks = [self._process_repo(sem, repo) for repo in repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        integrations: dict[str, RepoIntegrationData] = {}
        for result in results:
            if isinstance(result, GitHubAuthError):
                raise ConfigEntryAuthFailed from result
            if isinstance(result, Exception):
                _LOGGER.debug("Error processing repo: %s", result)
                continue
            if result is not None:
                for data in result:
                    integrations[data.domain] = data

        return integrations

    async def _process_repo(
        self, sem: asyncio.Semaphore, repo: dict
    ) -> list[RepoIntegrationData] | None:
        """Check a single repo for custom_components."""
        async with sem:
            repo_name = repo["name"]

            # Check for custom_components directory
            contents = await self.api.get_directory_contents(
                repo_name, "custom_components"
            )
            if not contents or not isinstance(contents, list):
                return None

            results: list[RepoIntegrationData] = []
            for entry in contents:
                if entry.get("type") != "dir":
                    continue
                domain = entry["name"]
                default_branch = repo.get("default_branch", "main")
                data = await self._process_domain(
                    repo_name, domain, default_branch
                )
                if data is not None:
                    results.append(data)

            return results if results else None

    async def _process_domain(
        self, repo_name: str, domain: str, default_branch: str = "main"
    ) -> RepoIntegrationData | None:
        """Process a single domain directory within a repo."""
        manifest_raw = await self.api.get_file_contents(
            repo_name, f"custom_components/{domain}/manifest.json"
        )
        if manifest_raw is None:
            return None

        try:
            manifest = json.loads(manifest_raw)
        except (json.JSONDecodeError, ValueError):
            _LOGGER.debug("Invalid manifest.json in %s/%s", repo_name, domain)
            return None

        if not all(k in manifest for k in ("domain", "name", "version")):
            _LOGGER.debug("Incomplete manifest in %s/%s", repo_name, domain)
            return None

        if manifest["domain"] != domain:
            _LOGGER.debug(
                "Domain mismatch in %s: dir=%s, manifest=%s",
                repo_name,
                domain,
                manifest["domain"],
            )
            return None

        # Try to get latest release
        release = await self.api.get_latest_release(repo_name)
        if release:
            latest_version = release["tag_name"].lstrip("v")
            release_url = release.get("html_url")
            release_notes = release.get("body")
            download_ref = release["tag_name"]
        else:
            latest_version = manifest["version"]
            release_url = None
            release_notes = None
            download_ref = default_branch

        return RepoIntegrationData(
            repo_full_name=f"{self.api.owner}/{repo_name}",
            domain=domain,
            name=manifest["name"],
            latest_version=latest_version,
            release_url=release_url,
            release_notes=release_notes,
            download_ref=download_ref,
            manifest=manifest,
        )
