"""Shared device info for Halo entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HaloCoordinator
from .models import HaloNode


def router_device_info(coordinator: HaloCoordinator) -> DeviceInfo:
    """Device registry entry for the mesh as a whole."""
    master = coordinator.data.master if coordinator.data else None
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        name=master.name if master and master.name else "Mercusys Halo",
        manufacturer="Mercusys",
        model=master.model if master else None,
        sw_version=master.firmware if master else None,
        configuration_url=coordinator.client.host,
    )


def node_device_info(coordinator: HaloCoordinator, node: HaloNode) -> DeviceInfo:
    """Device registry entry for one Halo unit."""
    return DeviceInfo(
        identifiers={(DOMAIN, node.mac)},
        name=node.name or node.mac,
        manufacturer="Mercusys",
        model=node.model,
        sw_version=node.firmware,
        via_device=(DOMAIN, coordinator.config_entry.entry_id),
    )


class HaloEntity(CoordinatorEntity[HaloCoordinator]):
    """Base entity attached to the mesh."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HaloCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = router_device_info(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        return router_device_info(self.coordinator)


class HaloNodeEntity(CoordinatorEntity[HaloCoordinator]):
    """Base entity attached to one discovered Halo unit."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HaloCoordinator, mac: str) -> None:
        super().__init__(coordinator)
        self._mac = mac

    @property
    def node(self) -> HaloNode | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.node(self._mac)

    @property
    def available(self) -> bool:
        return self.node is not None and super().available

    @property
    def device_info(self) -> DeviceInfo | None:
        node = self.node
        if node is None:
            return None
        return node_device_info(self.coordinator, node)
