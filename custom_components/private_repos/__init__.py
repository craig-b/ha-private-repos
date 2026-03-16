"""The Private Repos integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import (
    CONF_ACCOUNT_TYPE,
    CONF_GITHUB_PAT,
    CONF_GITHUB_USER,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .coordinator import PrivateReposCoordinator
from .github_api import GitHubAPI

PLATFORMS = [Platform.UPDATE]

type PrivateReposConfigEntry = ConfigEntry[PrivateReposCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: PrivateReposConfigEntry
) -> bool:
    """Set up Private Repos from a config entry."""
    session = async_get_clientsession(hass)
    api = GitHubAPI(
        session,
        entry.data[CONF_GITHUB_USER],
        entry.data[CONF_GITHUB_PAT],
        entry.data[CONF_ACCOUNT_TYPE],
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")

    coordinator = PrivateReposCoordinator(
        hass, entry, api, store, scan_interval
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PrivateReposConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
