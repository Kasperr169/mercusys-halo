"""The Mercusys Halo integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .api import HaloClient
from .const import DOMAIN
from .coordinator import HaloCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

type HaloConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: HaloConfigEntry) -> bool:
    """Set up Mercusys Halo from a config entry."""
    client = HaloClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PASSWORD],
        entry.data.get("verify_ssl", False),
    )
    coordinator = HaloCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HaloConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_reload(hass: HomeAssistant, entry: HaloConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
