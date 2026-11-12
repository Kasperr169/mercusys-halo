"""Device trackers for clients discovered on the mesh."""

from __future__ import annotations

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HaloCoordinator
from .entity import HaloEntity
from .models import HaloClientDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a tracker for each client MAC the panel reports."""
    coordinator: HaloCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _discover() -> None:
        if coordinator.data is None:
            return
        fresh = []
        for client in coordinator.data.clients:
            if client.mac in known:
                continue
            known.add(client.mac)
            fresh.append(HaloClientTracker(coordinator, client.mac))
        if fresh:
            async_add_entities(fresh)

    coordinator.async_add_listener(_discover)
    _discover()


class HaloClientTracker(HaloEntity, ScannerEntity):
    """Presence of one client. The name and MAC come from the panel."""

    _attr_has_entity_name = False

    def __init__(self, coordinator: HaloCoordinator, mac: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_client_{mac}"

    def _client(self) -> HaloClientDevice | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.client(self._mac)

    @property
    def name(self) -> str:
        client = self._client()
        if client and client.name:
            return client.name
        return self._mac

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        client = self._client()
        return bool(client and client.online)

    @property
    def ip_address(self) -> str | None:
        client = self._client()
        return client.ip if client else None

    @property
    def mac_address(self) -> str | None:
        client = self._client()
        return client.raw_mac if client else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        client = self._client()
        if client is None:
            return {}
        return {"connection": client.connection, "kind": client.kind, "node_id": client.node_id}
