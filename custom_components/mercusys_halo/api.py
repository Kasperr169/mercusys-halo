"""Local admin client for Mercusys Halo panels."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import secrets
import ssl
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import DEFAULT_TIMEOUT, MESH_DEVICE

_LOGGER = logging.getLogger(__name__)

_SUCCESS = "00000"


class HaloError(Exception):
    """Router returned something the client cannot use."""


class HaloAuthError(HaloError):
    """The owner password was rejected."""


class HaloConnectionError(HaloError):
    """The panel could not be reached."""


def normalize_host(value: str) -> str:
    """Turn a host or URL into an origin without a trailing slash."""
    raw = value.strip().rstrip("/")
    if not raw:
        raise HaloError("host is empty")
    if "://" not in raw:
        raw = f"https://{raw}"
    parts = urlsplit(raw)
    if not parts.hostname:
        raise HaloError("host is invalid")
    scheme = "https" if parts.scheme == "http" else parts.scheme
    return urlunsplit((scheme, parts.netloc, "", "", ""))


def norm_mac(value: str) -> str:
    """Compare MAC addresses without separators."""
    return re.sub(r"[^0-9A-Fa-f]", "", value).upper()


def encode_query_value(value: str) -> str:
    """Encode the session id the way the panel's browser does."""
    encoded: list[str] = []
    for char in value:
        code = ord(char)
        if code <= 31 or code >= 127 or char in " \"#<>":
            encoded.append(f"%{code:02X}")
        else:
            encoded.append(char)
    return "".join(encoded)


def _lines(text: str) -> list[str]:
    if text.endswith("\r\n"):
        text = text[:-2]
    return text.split("\r\n")


def _succeeded(text: str) -> bool:
    rows = _lines(text)
    return bool(rows) and rows[0] == _SUCCESS


def su_encrypt(seed: str, secret: str, dictionary: str) -> str:
    """Session id used by the Halo web panel."""
    length = max(len(seed), len(secret))
    output: list[str] = []
    for index in range(length):
        left = 0xBB
        right = 0xBB
        if index >= len(seed):
            right = ord(secret[index])
        elif index >= len(secret):
            left = ord(seed[index])
        else:
            left = ord(seed[index])
            right = ord(secret[index])
        output.append(dictionary[(left ^ right) % len(dictionary)])
    return "".join(output)


def _ssl_context(verify: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    # Halo's panel still offers legacy TLS renegotiation.
    legacy = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    context.options |= legacy
    return context


def _rsa_hex(plain: str, modulus: int, exponent: int, width: int) -> str:
    public = rsa.RSAPublicNumbers(exponent, modulus).public_key()
    encrypted = public.encrypt(plain.encode("utf-8"), padding.PKCS1v15())
    return encrypted.hex().zfill(width)


def _aes_encrypt(plain: str, key: str, iv: str) -> str:
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plain.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8")))
    encryptor = cipher.encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("ascii")


def _aes_decrypt(payload: str, key: str, iv: str) -> str:
    raw = base64.b64decode(payload.strip())
    cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8")))
    decryptor = cipher.decryptor()
    padded = decryptor.update(raw) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


def _digits(count: int) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(count))


class HaloClient:
    """One logged-in conversation with a Halo panel.

    The panel allows a single admin session. Callers must use ``session()``
    so login, requests, and logout stay together.
    """

    def __init__(self, host: str, password: str, verify_ssl: bool, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.host = normalize_host(host)
        self._password = password
        self._verify_ssl = verify_ssl
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()
        self._http: aiohttp.ClientSession | None = None
        self._session_id = ""
        self._aes_key = ""
        self._aes_iv = ""
        self._key_material = ""
        self._seq = 0
        self._modulus = 0
        self._exponent = 0
        self._rsa_width = 0

    @asynccontextmanager
    async def session(self):
        """Log in, run the caller's requests, then log out."""
        async with self._lock:
            await self._open()
            try:
                await self._login()
                yield self
            finally:
                try:
                    await self._logout()
                except HaloError:
                    _LOGGER.debug("Logout did not complete")
                await self._close()

    async def async_discover(self) -> list[dict[str, Any]]:
        """Return the mesh nodes, used while setting up the config entry."""
        async with self.session():
            payload = await self.read("/admin/device?form=device_list")
        devices = payload.get("device_list")
        if not isinstance(devices, list) or not devices:
            raise HaloError("device list was empty")
        return devices

    async def read(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read one panel form."""
        body: dict[str, Any] = {"operation": "read"}
        if params:
            body["params"] = params
        return await self.command(path, body)

    async def command(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """Send an encrypted JSON command and return the result object."""
        if self._http is None or not self._session_id:
            raise HaloError("not logged in")
        encrypted = _aes_encrypt(_json(body), self._aes_key, self._aes_iv)
        signature = self._signature(self._seq + len(encrypted))
        form = f"sign={signature}&data={encrypted}"
        status, text = await self._post(
            self._with_id(path),
            form,
            "application/x-www-form-urlencoded; charset=UTF-8",
        )
        if status == 401:
            raise HaloAuthError("session expired")
        try:
            decoded = _aes_decrypt(text, self._aes_key, self._aes_iv)
        except (ValueError, TypeError) as err:
            raise HaloError(f"{path} returned HTTP {status}") from err
        payload = _loads(decoded)
        error_code = payload.get("error_code")
        if error_code not in (0, None):
            raise HaloError(f"{path} failed with error {error_code}")
        result = payload.get("result")
        return result if isinstance(result, dict) else payload

    async def set_wifi(self, enabled: bool) -> None:
        """Turn the whole wireless network on or off."""
        await self.command(
            "/admin/network?form=wifi_network",
            {"operation": "write", "params": {"enable_wfnetwork": enabled}},
        )

    async def reboot(self, macs: list[str]) -> None:
        """Restart the Halo nodes identified by the MAC addresses from the panel."""
        await self.command(
            "/admin/device?form=system",
            {"operation": "reboot", "params": {"mac_list": [{"mac": mac} for mac in macs]}},
        )

    async def check_firmware(self) -> dict[str, Any]:
        """Ask the panel to look for firmware updates."""
        return await self.command("/admin/cloud?form=firmware_status", {"operation": "check"})

    def mesh_params(self) -> dict[str, str]:
        """Parameters the panel sends when a form covers the whole mesh."""
        return {"device_mac": MESH_DEVICE}

    async def _login(self) -> None:
        status, challenge = await self._post("/?code=7&asyn=1", "", "text/plain;charset=UTF-8")
        if status not in (200, 401):
            raise HaloConnectionError(f"challenge failed with HTTP {status}")
        rows = _lines(challenge)
        if len(rows) < 5 or not rows[4]:
            raise HaloConnectionError("challenge was incomplete")

        status, enabled = await self._post("/?code=16&asyn=0", "enable", "text/plain;charset=UTF-8")
        if status != 200 or not _succeeded(enabled):
            raise HaloConnectionError("encryption setup was refused")

        status, keys = await self._post("/?code=16&asyn=0", "get", "text/plain;charset=UTF-8")
        key_rows = _lines(keys)
        if status != 200 or len(key_rows) < 4 or key_rows[0] != _SUCCESS:
            raise HaloConnectionError("encryption key was refused")

        modulus_hex = key_rows[2]
        self._exponent = int(key_rows[1], 16)
        self._modulus = int(modulus_hex, 16)
        self._rsa_width = len(modulus_hex)
        self._seq = int(key_rows[3])
        digest = hashlib.md5(self._password.encode("utf-8")).hexdigest()
        self._session_id = su_encrypt(rows[3], digest, rows[4])
        password_token = _rsa_hex(self._password, self._modulus, self._exponent, self._rsa_width)
        status, login = await self._post(
            f"/?code=7&asyn=0&id={encode_query_value(self._session_id)}",
            password_token,
            "text/plain;charset=UTF-8",
        )
        if not _succeeded(login):
            raise HaloAuthError("login failed")

        self._aes_key = _digits(16)
        self._aes_iv = _digits(16)
        self._key_material = f"k={self._aes_key}&i={self._aes_iv}"
        key_token = _rsa_hex(self._key_material, self._modulus, self._exponent, self._rsa_width)
        status, armed = await self._post(
            f"/?code=16&asyn=0&id={encode_query_value(self._session_id)}",
            f"set {key_token}",
            "text/plain;charset=UTF-8",
        )
        if status != 200 or not _succeeded(armed):
            raise HaloAuthError("session key was refused")

    async def _logout(self) -> None:
        if not self._session_id or self._http is None:
            return
        await self._post(
            f"/?code=11&asyn=0&id={encode_query_value(self._session_id)}",
            "",
            "text/plain;charset=UTF-8",
        )

    def _signature(self, seq_and_length: int) -> str:
        payload = f"{self._key_material}&s={seq_and_length}"
        signature = ""
        for offset in range(0, len(payload), 53):
            signature += _rsa_hex(
                payload[offset : offset + 53],
                self._modulus,
                self._exponent,
                self._rsa_width,
            )
        return signature

    def _with_id(self, path: str) -> str:
        separator = "&" if "?" in path else "?"
        return f"{path}{separator}id={encode_query_value(self._session_id)}"

    async def _open(self) -> None:
        connector = aiohttp.TCPConnector(ssl=_ssl_context(self._verify_ssl))
        self._http = aiohttp.ClientSession(timeout=self._timeout, connector=connector)

    async def _close(self) -> None:
        http = self._http
        self._http = None
        self._session_id = ""
        if http is not None:
            await http.close()

    async def _post(self, path: str, body: str, content_type: str) -> tuple[int, str]:
        if self._http is None:
            raise HaloConnectionError("connection is closed")
        url = self.host + (path if path.startswith("/") else f"/{path}")
        try:
            async with self._http.post(
                url,
                data=body.encode("utf-8"),
                headers={
                    "Content-Type": content_type,
                    "X-Requested-With": "XMLHttpRequest",
                },
                allow_redirects=False,
            ) as response:
                return response.status, await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HaloConnectionError(str(err)) from err


def _json(body: dict[str, Any]) -> str:
    import json

    return json.dumps(body, separators=(",", ":"))


def _loads(text: str) -> dict[str, Any]:
    import json

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise HaloError("response was not an object")
    return payload
