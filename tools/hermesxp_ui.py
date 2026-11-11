"""Minimal authenticated client for the HermesXP screen/control listener.

The XP companion expects a 64-digit hex token in X-Hermes-Token.
This client deliberately limits inputs to what the companion accepts.
"""

from __future__ import annotations

import http.client
import ipaddress
import re
from dataclasses import dataclass


_ALLOWED_KEYS = frozenset((
    "Enter", "Tab", "Esc", "Backspace", "Delete",
    "Left", "Up", "Right", "Down",
))
_SERVICE_ACTIONS = frozenset(("status", "start", "stop", "restart"))
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024


class ResponseTooLargeError(RuntimeError):
    """A paired XP response exceeded the fixed client memory limit."""


_SERVICE_NAME = re.compile(r"[A-Za-z0-9_.+$\-](?:[A-Za-z0-9_.+$ \-]{0,78}[A-Za-z0-9_.+$\-])?\Z")


def validate_token(token: str) -> str:
    return isinstance(token, str) and re.fullmatch(r"[0-9a-fA-F]{64}", token) is not None


def validate_click(
    x: int, y: int, width: int, height: int, button: str = "left"
) -> tuple[int, int, str]:
    if (
        any(type(v) is not int for v in (x, y, width, height))
        or width < 1 or height < 1
        or not 0 <= x < width or not 0 <= y < height
        or button not in ("left", "right")
    ):
        raise ValueError("Click must have in-bounds integer coordinates and left/right button")
    return x, y, button


def validate_drag(x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> tuple[int, int, int, int]:
    validate_click(x1, y1, width, height)
    validate_click(x2, y2, width, height)
    return x1, y1, x2, y2


def validate_scroll(x: int, y: int, width: int, height: int, delta: int) -> tuple[int, int, int]:
    validate_click(x, y, width, height)
    if type(delta) is not int or delta == 0 or not -5 <= delta <= 5:
        raise ValueError("Scroll delta must be an integer from -5 to -1 or 1 to 5")
    return x, y, delta


def validate_text(text: str) -> bytes:
    if not isinstance(text, str) or not 1 <= len(text) <= 128:
        raise ValueError("Text must contain 1–128 characters")
    if any(not 32 <= ord(char) <= 126 for char in text):
        raise ValueError("Text may only contain printable ASCII characters")
    return text.encode("ascii")


def validate_key(key: str) -> bytes:
    if key not in _ALLOWED_KEYS:
        raise ValueError("Unsupported key name")
    return key.encode("ascii")


def validate_service_command(name: str, action: str) -> bytes:
    """Typed Windows SCM action; never interpreted as a shell command."""
    if not isinstance(name, str) or not _SERVICE_NAME.fullmatch(name):
        raise ValueError("Service name must be 1–80 safe ASCII characters")
    if action not in _SERVICE_ACTIONS:
        raise ValueError("Service action must be status, start, stop, or restart")
    return f"action={action}&name={name}".encode("ascii")


@dataclass
class HermesXPClient:
    host: str
    token: str
    port: int = 18768
    timeout: float = 5.0

    def __post_init__(self) -> None:
        address = ipaddress.ip_address(self.host)
        if address.version != 4 or not (address.is_private or address.is_loopback):
            raise ValueError("HermesXP host must be a private or loopback IPv4 address")
        if not validate_token(self.token):
            raise ValueError("HermesXP token must be exactly 64 hexadecimal characters")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Invalid port")

    def _request(self, method: str, path: str, body: bytes = b"") -> bytes:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(
                method, path, body=body,
                headers={"X-Hermes-Token": self.token, "Content-Length": str(len(body))},
            )
            response = connection.getresponse()
            payload = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(payload) > _MAX_RESPONSE_BYTES:
                raise ResponseTooLargeError("HermesXP response exceeds the 32 MiB limit")
            if response.status != 200:
                raise RuntimeError(f"HermesXP returned HTTP {response.status}: {payload[:120]!r}")
            return payload
        finally:
            connection.close()

    def _post_ack(self, path: str, body: bytes, expected: str) -> str:
        response = self._request("POST", path, body).decode("ascii", "replace").strip()
        if response != expected:
            raise RuntimeError("HermesXP did not acknowledge the requested mouse action")
        return response

    def screenshot(self) -> bytes:
        return self._request("GET", "/screenshot.bmp")

    def inspect(self) -> str:
        return self._request("GET", "/ui/inspect").decode("ascii", "replace")

    def click(self, x: int, y: int, width: int, height: int, button: str = "left") -> str:
        x, y, button = validate_click(x, y, width, height, button)
        payload = f"x={x}&y={y}&button={button}".encode("ascii")
        return self._request("POST", "/ui/click", payload).decode("ascii", "replace")

    def double_click(self, x: int, y: int, width: int, height: int) -> str:
        x, y, _button = validate_click(x, y, width, height, "left")
        body = f"x={x}&y={y}&button=left".encode("ascii")
        return self._post_ack("/ui/double-click", body, "double-clicked")

    def drag(self, x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> str:
        x1, y1, x2, y2 = validate_drag(x1, y1, x2, y2, width, height)
        body = f"x1={x1}&y1={y1}&x2={x2}&y2={y2}".encode("ascii")
        return self._post_ack("/ui/drag", body, "dragged")

    def scroll(self, x: int, y: int, width: int, height: int, delta: int) -> str:
        x, y, delta = validate_scroll(x, y, width, height, delta)
        body = f"x={x}&y={y}&delta={delta}".encode("ascii")
        return self._post_ack("/ui/scroll", body, "scrolled")

    def type_text(self, text: str) -> str:
        return self._request("POST", "/ui/type", validate_text(text)).decode("ascii", "replace")

    def key(self, name: str) -> str:
        return self._request("POST", "/ui/key", validate_key(name)).decode("ascii", "replace")

    def service(self, name: str, action: str = "status") -> str:
        """Operate on any installed Windows service using SCM permissions."""
        return self._request("POST", "/system/service",
                             validate_service_command(name, action)).decode("ascii", "replace")

    def network_status(self) -> str:
        """Read authenticated XP discovery status without exposing secrets."""
        return self._request("GET", "/network/status").decode("ascii", "replace")


def request(
    host: str, path: str, token: str, body: bytes = b"", *, port: int = 18768,
    timeout: float = 5.0,
) -> tuple[str, bytes]:
    """Make an authenticated local control call, returning type and raw response."""
    client = HermesXPClient(host=host, token=token, port=port, timeout=timeout)
    if path not in ("/ui/inspect", "/ui/click", "/ui/double-click", "/ui/drag", "/ui/scroll",
                    "/ui/type", "/ui/key", "/screenshot.bmp", "/system/service", "/network/status"):
        raise ValueError("Unsupported endpoint")
    if not isinstance(body, bytes):
        raise ValueError("Request body must be bytes")
    method = "GET" if path in ("/ui/inspect", "/screenshot.bmp", "/network/status") else "POST"
    connection = http.client.HTTPConnection(client.host, client.port, timeout=client.timeout)
    try:
        connection.request(
            method, path, body=body,
            headers={"X-Hermes-Token": client.token, "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        payload = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(payload) > _MAX_RESPONSE_BYTES:
            raise ResponseTooLargeError("HermesXP response exceeds the 32 MiB limit")
        if response.status != 200:
            raise RuntimeError(f"HermesXP returned HTTP {response.status}: {payload[:120]!r}")
        return response.getheader("Content-Type", ""), payload
    finally:
        connection.close()
