"""Data update coordinator for Mercusys Halo."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HaloAuthError, HaloClient, HaloConnectionError, HaloError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .models import (
    HaloSnapshot,
    internet_online,
    lan_ip,
    parse_bands,
    parse_clients,
    parse_firmware,
    parse_nodes,
    wan_ip,
    wifi_enabled,
)

_LOGGER = logging.getLogger(__name__)


class HaloCoordinator(DataUpdateCoordinator[HaloSnapshot]):
    """Poll the panel and expose actions that need the same login."""

    def __init__(self, hass: HomeAssistant, entry, client: HaloClient) -> None:
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name="Mercusys Halo",
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )
        self.client = client
        self.firmware_checked = False
        self._firmware: list = []

    async def _async_update_data(self) -> HaloSnapshot:
        try:
            async with self.client.session():
                internet = await self.client.read("/admin/network?form=internet")
                wan = await self.client.read("/admin/network?form=wan_ipv4")
                lan = await self.client.read(
                    "/admin/network?form=lan_ip",
                    self.client.mesh_params(),
                )
                wireless_switch = await self.client.read("/admin/network?form=wifi_network")
                wireless = await self.client.read("/admin/wireless?form=wlan")
                clients = await self.client.read(
                    "/admin/client?form=client_list",
                    self.client.mesh_params(),
                )
                devices = await self.client.read("/admin/device?form=device_list")
        except HaloAuthError as err:
            raise ConfigEntryAuthFailed("owner password was rejected") from err
        except (HaloConnectionError, HaloError) as err:
            raise UpdateFailed(str(err)) from err

        return HaloSnapshot(
            internet_online=internet_online(internet),
            wan_ip=wan_ip(wan),
            lan_ip=lan_ip(lan),
            wifi_enabled=wifi_enabled(wireless_switch),
            bands=parse_bands(wireless),
            nodes=parse_nodes(devices),
            clients=parse_clients(clients),
            firmware=list(self._firmware),
            firmware_checked=self.firmware_checked,
        )

    async def async_set_wifi(self, enabled: bool) -> None:
        """Turn the whole wireless network on or off, then refresh."""
        try:
            async with self.client.session():
                await self.client.set_wifi(enabled)
        except HaloAuthError as err:
            raise ConfigEntryAuthFailed("owner password was rejected") from err
        except (HaloConnectionError, HaloError) as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()

    async def async_reboot(self, macs: list[str]) -> None:
        """Restart the given Halo nodes. MAC addresses come from the last poll."""
        if not macs:
            raise UpdateFailed("no Halo units to restart")
        try:
            async with self.client.session():
                await self.client.reboot(macs)
        except HaloAuthError as err:
            raise ConfigEntryAuthFailed("owner password was rejected") from err
        except HaloConnectionError:
            _LOGGER.debug("Reboot closed the panel connection")
        except HaloError as err:
            raise UpdateFailed(str(err)) from err

    async def async_check_firmware(self) -> None:
        """Look for firmware updates and keep the result for the update entities."""
        try:
            async with self.client.session():
                payload = await self.client.check_firmware()
        except HaloAuthError as err:
            raise ConfigEntryAuthFailed("owner password was rejected") from err
        except (HaloConnectionError, HaloError) as err:
            raise UpdateFailed(str(err)) from err
        self._firmware = parse_firmware(payload)
        self.firmware_checked = True
        if self.data is not None:
            self.data.firmware = list(self._firmware)
            self.data.firmware_checked = True
        self.async_update_listeners()
