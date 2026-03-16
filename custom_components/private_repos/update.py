"""Update platform for Private Repos integration."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import logging
import os
import shutil
import tempfile
from typing import Any
import zipfile

from homeassistant.components.persistent_notification import async_create
from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ACCOUNT_TYPE, CONF_GITHUB_USER, DOMAIN
from .coordinator import PrivateReposCoordinator, RepoIntegrationData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up update entities from a config entry."""
    coordinator: PrivateReposCoordinator = entry.runtime_data
    known_domains: set[str] = set()

    @callback
    def _async_add_new_entities() -> None:
        """Add entities for newly discovered domains."""
        if coordinator.data is None:
            return
        new_domains = set(coordinator.data) - known_domains
        if not new_domains:
            return
        known_domains.update(new_domains)
        async_add_entities(
            PrivateIntegrationUpdateEntity(coordinator, domain)
            for domain in new_domains
        )

    _async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))


class PrivateIntegrationUpdateEntity(
    CoordinatorEntity[PrivateReposCoordinator], UpdateEntity
):
    """Update entity for a private integration."""

    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.RELEASE_NOTES
        | UpdateEntityFeature.PROGRESS
    )

    def __init__(
        self,
        coordinator: PrivateReposCoordinator,
        domain: str,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator)
        self._integration_domain = domain
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{domain}"
        self._installing = False
        self._install_progress: int | None = None

        entry = coordinator.config_entry
        github_user = entry.data[CONF_GITHUB_USER]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=f"Private Repos ({github_user})",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _data(self) -> RepoIntegrationData | None:
        """Get the current data for this integration."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._integration_domain)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        if self._data:
            return self._data.name
        return self._integration_domain

    @property
    def installed_version(self) -> str | None:
        """Return the installed version."""
        installed = self.coordinator.installed.get(self._integration_domain)
        if installed:
            return installed.get("installed_version")
        return None

    @property
    def latest_version(self) -> str | None:
        """Return the latest version."""
        if self._data:
            return self._data.latest_version
        return self.installed_version

    @property
    def release_url(self) -> str | None:
        """Return the release URL."""
        if self._data:
            return self._data.release_url
        return None

    @property
    def in_progress(self) -> bool:
        """Return if an install is in progress."""
        return self._installing

    @property
    def update_percentage(self) -> int | None:
        """Return install progress percentage."""
        return self._install_progress

    @property
    def title(self) -> str | None:
        """Return the title of the software."""
        if self._data:
            return self._data.name
        return None

    async def async_release_notes(self) -> str | None:
        """Return release notes."""
        if self._data and self._data.release_notes:
            return self._data.release_notes
        return None

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install the update."""
        data = self._data
        if data is None:
            return

        lock = self.coordinator.get_install_lock(self._integration_domain)
        async with lock:
            self._installing = True
            self._install_progress = 0
            self.async_write_ha_state()

            try:
                await self._do_install(data)
            finally:
                self._installing = False
                self._install_progress = None
                self.async_write_ha_state()

    async def _do_install(self, data: RepoIntegrationData) -> None:
        """Perform the actual installation."""
        domain = self._integration_domain
        hass = self.hass

        # Download zipball
        self._install_progress = 10
        self.async_write_ha_state()
        zipball = await self.coordinator.api.download_zipball(
            data.repo_full_name.split("/", 1)[1], data.download_ref
        )

        # Extract to temp dir
        self._install_progress = 40
        self.async_write_ha_state()

        target = hass.config.path("custom_components", domain)

        def _extract_and_copy() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                zf = zipfile.ZipFile(io.BytesIO(zipball))
                zf.extractall(tmpdir)

                # Find custom_components/{domain}/ inside the extracted tree
                source = None
                for root, dirs, _files in os.walk(tmpdir):
                    if os.path.basename(root) == domain and os.path.basename(
                        os.path.dirname(root)
                    ) == "custom_components":
                        source = root
                        break

                if source is None:
                    raise RuntimeError(
                        f"Could not find custom_components/{domain}/ in zipball"
                    )

                # Remove existing and copy new
                if os.path.exists(target):
                    shutil.rmtree(target)
                shutil.copytree(source, target)

        await hass.async_add_executor_job(_extract_and_copy)

        self._install_progress = 70
        self.async_write_ha_state()

        # Update installed record
        self.coordinator.installed[domain] = {
            "installed_version": data.latest_version,
            "repo": data.repo_full_name,
            "installed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.coordinator.async_save_installed()

        self._install_progress = 90
        self.async_write_ha_state()

        # Create persistent notification
        async_create(
            hass,
            f"**{data.name}** ({domain}) has been installed/updated to version "
            f"**{data.latest_version}**. A restart is required.",
            title="Integration update installed",
            notification_id=f"private_repos_restart_{domain}",
        )

        self._install_progress = 100
        self.async_write_ha_state()
