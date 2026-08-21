"""eToro integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EToroApiClient
from .const import CONF_API_KEY, CONF_ENVIRONMENT, CONF_USER_KEY, DEFAULT_SCAN_INTERVAL, DOMAIN, ENV_REAL, PLATFORMS
from .coordinator import EToroCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up eToro from a config entry."""
    session = async_get_clientsession(hass)
    environment = entry.data.get(CONF_ENVIRONMENT, ENV_REAL)

    client = EToroApiClient(
        api_key=entry.data[CONF_API_KEY],
        user_key=entry.data[CONF_USER_KEY],
        environment=environment,
        session=session,
    )

    scan_interval = entry.options.get(
        "scan_interval", entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    )

    coordinator = EToroCoordinator(hass, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update (e.g. scan interval change)."""
    await hass.config_entries.async_reload(entry.entry_id)
