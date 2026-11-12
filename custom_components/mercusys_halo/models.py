"""Snapshots built from the Halo panel."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from .api import norm_mac


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def decode_label(value: Any) -> str:
    """Decode names the panel stores as base64, and leave plain text alone."""
    text = _text(value).strip()
    if not text:
        return ""
    try:
        decoded = base64.b64decode(text, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return text
    if decoded and decoded.isprintable():
        return decoded
    return text


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "on", "online", "connected"}
    return bool(value)


@dataclass(slots=True)
class HaloNode:
    """One Halo unit reported by the panel."""

    mac: str
    raw_mac: str
    name: str
    model: str | None
    role: str | None
    firmware: str | None
    hardware: str | None
    ip: str | None
    online: bool
    connection: str | None


@dataclass(slots=True)
class HaloClientDevice:
    """A phone, computer, or other client on the mesh."""

    mac: str
    raw_mac: str
    name: str
    ip: str | None
    online: bool
    connection: str | None
    kind: str | None
    node_id: str | None


@dataclass(slots=True)
class RadioBand:
    """One wireless band, host and guest, as reported by the panel."""

    key: str
    label: str
    host_enabled: bool
    guest_enabled: bool
    channel: str | None
    ssid: str | None
    guest_ssid: str | None


@dataclass(slots=True)
class FirmwareOffer:
    """One row from a firmware check."""

    mac: str
    installed: str | None
    latest: str | None
    needs_upgrade: bool


@dataclass(slots=True)
class HaloSnapshot:
    """Everything collected during one poll."""

    internet_online: bool
    wan_ip: str | None
    lan_ip: str | None
    wifi_enabled: bool
    bands: list[RadioBand] = field(default_factory=list)
    nodes: list[HaloNode] = field(default_factory=list)
    clients: list[HaloClientDevice] = field(default_factory=list)
    firmware: list[FirmwareOffer] = field(default_factory=list)
    firmware_checked: bool = False

    @property
    def master(self) -> HaloNode | None:
        for node in self.nodes:
            if node.role == "master":
                return node
        return self.nodes[0] if self.nodes else None

    def node(self, mac: str) -> HaloNode | None:
        wanted = norm_mac(mac)
        for node in self.nodes:
            if node.mac == wanted:
                return node
        return None

    def client(self, mac: str) -> HaloClientDevice | None:
        wanted = norm_mac(mac)
        for client in self.clients:
            if client.mac == wanted:
                return client
        return None

    def firmware_for(self, mac: str) -> FirmwareOffer | None:
        wanted = norm_mac(mac)
        for offer in self.firmware:
            if offer.mac == wanted:
                return offer
        return None


def _band_label(key: str) -> str:
    if key == "band2_4":
        return "2.4 GHz"
    if key == "band5_1":
        return "5 GHz"
    if key == "band5_2":
        return "5 GHz 2"
    if key == "band6":
        return "6 GHz"
    return key.removeprefix("band").replace("_", " ")


def _connection(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def parse_nodes(payload: dict[str, Any]) -> list[HaloNode]:
    """Build nodes from a device_list result."""
    rows = payload.get("device_list")
    if not isinstance(rows, list):
        return []
    nodes: list[HaloNode] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_mac = _text(row.get("mac"))
        if not raw_mac:
            continue
        name = _text(row.get("nickname")) or raw_mac
        nodes.append(
            HaloNode(
                mac=norm_mac(raw_mac),
                raw_mac=raw_mac,
                name=name,
                model=_text(row.get("device_model")) or None,
                role=_text(row.get("role")) or None,
                firmware=_text(row.get("software_ver")) or None,
                hardware=_text(row.get("hardware_ver")) or None,
                ip=_text(row.get("device_ip")) or None,
                online=_text(row.get("group_status")) == "connected",
                connection=_connection(row.get("connection_type")),
            )
        )
    return nodes


def parse_clients(payload: dict[str, Any]) -> list[HaloClientDevice]:
    """Build clients from a client_list result."""
    rows = payload.get("client_list")
    if not isinstance(rows, list):
        return []
    clients: list[HaloClientDevice] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_mac = _text(row.get("mac"))
        if not raw_mac:
            continue
        linked = row.get("linked_device_info")
        node_id = ""
        connection = _text(row.get("connection_type")) or None
        if isinstance(linked, dict):
            node_id = _text(linked.get("device_id"))
            connection = connection or _text(linked.get("connection_type")) or None
        name = decode_label(row.get("name")) or raw_mac
        clients.append(
            HaloClientDevice(
                mac=norm_mac(raw_mac),
                raw_mac=raw_mac,
                name=name,
                ip=_text(row.get("ip")) or None,
                online=_as_bool(row.get("online")),
                connection=connection,
                kind=_text(row.get("client_type")) or None,
                node_id=node_id or None,
            )
        )
    return clients


def parse_bands(payload: dict[str, Any]) -> list[RadioBand]:
    """Build radio bands from the wireless status result."""
    bands: list[RadioBand] = []
    for key, value in payload.items():
        if not key.startswith("band") or not isinstance(value, dict):
            continue
        host = value.get("host") if isinstance(value.get("host"), dict) else {}
        guest = value.get("guest") if isinstance(value.get("guest"), dict) else {}
        bands.append(
            RadioBand(
                key=key,
                label=_band_label(key),
                host_enabled=_as_bool(host.get("enable")),
                guest_enabled=_as_bool(guest.get("enable")),
                channel=_text(host.get("channel")) or None,
                ssid=decode_label(host.get("ssid")) or None,
                guest_ssid=decode_label(guest.get("ssid")) or None,
            )
        )
    return bands


def parse_firmware(payload: dict[str, Any]) -> list[FirmwareOffer]:
    """Build firmware offers from a check result."""
    rows = payload.get("fw_list") or payload.get("device_list") or []
    if not isinstance(rows, list):
        return []
    offers: list[FirmwareOffer] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_mac = _text(row.get("mac"))
        if not raw_mac:
            continue
        installed = _text(row.get("software_ver")) or None
        latest = _text(row.get("new_version")) or None
        needs = _as_bool(row.get("need_to_upgrade"))
        offers.append(
            FirmwareOffer(
                mac=norm_mac(raw_mac),
                installed=installed,
                latest=latest or installed,
                needs_upgrade=needs,
            )
        )
    return offers


def internet_online(payload: dict[str, Any]) -> bool:
    """Return whether IPv4 internet is online."""
    ipv4 = payload.get("ipv4")
    if not isinstance(ipv4, dict):
        return False
    return _text(ipv4.get("inet_status")).lower() == "online"


def wan_ip(payload: dict[str, Any]) -> str | None:
    """Return the WAN address from a wan_ipv4 result."""
    wan = payload.get("wan")
    if isinstance(wan, dict):
        info = wan.get("ip_info")
        if isinstance(info, dict) and info.get("ip"):
            return _text(info.get("ip"))
    return None


def lan_ip(payload: dict[str, Any]) -> str | None:
    """Return the LAN address from a lan_ip result."""
    lan = payload.get("lan_ip")
    if isinstance(lan, dict) and lan.get("ip"):
        return _text(lan.get("ip"))
    return None


def wifi_enabled(payload: dict[str, Any]) -> bool:
    """Return the whole-network wireless switch."""
    return _as_bool(payload.get("enable_wfnetwork"))
