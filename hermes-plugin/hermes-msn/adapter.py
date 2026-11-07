"""Hermes XP/MSN platform adapter.

Local JSON-lines bridge: 127.0.0.1:18764 (authentication with a random token).
Optional LAN-only XP connection probe: configurable bind IP:18765, *no secrets*.

Designed for Hermes' documented platform plugin API; not a standalone service.
"""
import asyncio
import hmac
import json
import logging
import os
import re
import uuid

from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.platforms.event import MessageEvent, MessageType
from gateway.platforms._shared import extra_or_secret, get_scoped_secret, seed_extra_from_env
from gateway.config import Platform, PlatformConfig
from gateway.session import SessionSource

log = logging.getLogger(__name__)

BRIDGE_PORT = 18764
PROBE_PORT = 18765
SAFE_HOSTNAME = re.compile(r"[A-Za-z0-9-]{1,63}\Z")


class MSNPlatformAdapter(BasePlatformAdapter):
    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform("hermes_msn"))
        extra = getattr(config, "extra", None)
        self.secret = extra_or_secret(extra, "token", "HERMES_MSN_BRIDGE_TOKEN") or ""
        self.owner = str(extra_or_secret(extra, "owner_email", "HERMES_MSN_OWNER_EMAIL") or "").strip().lower()
        self.bridge_server = None
        self.probe_server = None
        self.bridge_writer = None
        self._bridge_tasks = set()
        self._write_lock = asyncio.Lock()

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        if len(self.secret) < 32 or not self.owner or "@" not in self.owner:
            log.error("MSN bridge secret must be >=32 chars and owner address must be configured")
            return False
        self.bridge_server = await asyncio.start_server(self._on_bridge, "127.0.0.1", BRIDGE_PORT, limit=16384)
        probe_host = os.environ.get("HERMES_XP_PROBE_BIND", "").strip()
        if probe_host:
            # Do not expose on all interfaces by accident; require a literal IPv4 LAN address.
            import ipaddress
            address = ipaddress.ip_address(probe_host)
            if address.version != 4 or not (address.is_private or address.is_loopback):
                self.bridge_server.close()
                await self.bridge_server.wait_closed()
                raise ValueError("HERMES_XP_PROBE_BIND must be a private IPv4 LAN address")
            self.probe_server = await asyncio.start_server(self._on_probe, probe_host, PROBE_PORT, limit=1024)
            log.info("XP connectivity probe listening at %s:%d (unauthenticated, no commands)", probe_host, PROBE_PORT)
        self._mark_connected()
        return True

    async def _on_probe(self, reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            line = line.decode("ascii", "replace").strip()
            if line.startswith("HXP1 ") and SAFE_HOSTNAME.fullmatch(line[5:]):
                log.info("XP probe from %s named %s", writer.get_extra_info("peername"), line[5:])
                writer.write(b"HXP1 OK\r\n")
            else:
                writer.write(b"HXP1 BAD\r\n")
            await writer.drain()
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def _on_bridge(self, reader, writer):
        if self.bridge_writer is not None:
            writer.close()
            await writer.wait_closed()
            return
        authorized = False
        task = asyncio.current_task()
        self._bridge_tasks.add(task)
        try:
            data = await asyncio.wait_for(reader.readline(), timeout=5.0)
            request = json.loads(data)
            supplied = request.get("token", "") if isinstance(request, dict) else ""
            if not isinstance(request, dict) or not isinstance(supplied, str) or request.get("type") != "hello" or not hmac.compare_digest(supplied, self.secret):
                log.warning("Rejecting unauthorized local MSN bridge")
                return
            authorized = True
            self.bridge_writer = writer
            writer.write(b'{"type":"hello_ok"}\n')
            await writer.drain()
            log.info("Local MSN bridge connected")
            while True:
                data = await reader.readline()
                if not data:
                    break
                try:
                    msg = json.loads(data)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(msg, dict) or msg.get("type") != "incoming":
                    continue
                sender = str(msg.get("sender", "")).lower().strip()
                body = msg.get("body", "")
                # Fail closed: even other contacts on Escargot must never trigger tools.
                if sender != self.owner or not isinstance(body, str) or not body.strip():
                    continue
                body = body[:4000]
                event = MessageEvent(
                    text=body,
                    message_type=MessageType.TEXT,
                    user_id=sender,
                    user_name=sender,
                    message_id=str(uuid.uuid4()),
                    source=SessionSource(platform=Platform("hermes_msn"), chat_id=sender,
                                         chat_type="dm", user_id=sender, user_name=sender),
                )
                await self.handle_message(event)
        except (ValueError, UnicodeDecodeError, OSError, asyncio.IncompleteReadError) as err:
            log.warning("MSN bridge error: %s", err)
        finally:
            if authorized and writer is self.bridge_writer:
                self.bridge_writer = None
            self._bridge_tasks.discard(task)
            writer.close()
            await writer.wait_closed()

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        chat_id = str(chat_id).strip().lower()
        if chat_id != self.owner:
            return SendResult(success=False, error="Recipient not authorized")
        async with self._write_lock:
            if not self.bridge_writer or self.bridge_writer.is_closing():
                return SendResult(success=False, error="MSN bridge is offline", retryable=True)
            try:
                text = str(content)
                self.bridge_writer.write((json.dumps({"type":"send", "to":chat_id, "text":text[:4000]},
                                                     ensure_ascii=False)+"\n").encode("utf-8"))
                await self.bridge_writer.drain()
                return SendResult(success=True, message_id=str(uuid.uuid4()))
            except OSError as err:
                return SendResult(success=False, error=str(err), retryable=True)

    async def get_chat_info(self, chat_id):
        return {"name": str(chat_id), "type": "dm"}

    async def disconnect(self):
        if self.bridge_writer:
            self.bridge_writer.close()
            self.bridge_writer = None
        for task in list(self._bridge_tasks):
            task.cancel()
        for server in (self.bridge_server, self.probe_server):
            if server:
                server.close()
                await server.wait_closed()
        self._mark_disconnected()


def check_requirements() -> bool:
    return bool(get_scoped_secret("HERMES_MSN_BRIDGE_TOKEN") and get_scoped_secret("HERMES_MSN_OWNER_EMAIL"))


def validate_config(config) -> bool:
    extra = getattr(config, "extra", None)
    return bool(extra_or_secret(extra, "token", "HERMES_MSN_BRIDGE_TOKEN") and
                extra_or_secret(extra, "owner_email", "HERMES_MSN_OWNER_EMAIL"))


def _env_enablement():
    if not check_requirements():
        return None
    return seed_extra_from_env((("HERMES_MSN_BRIDGE_TOKEN", "token", None),
                                ("HERMES_MSN_OWNER_EMAIL", "owner_email", None)))


def register(ctx):
    ctx.register_platform(
        name="hermes_msn", label="Hermes XP MSN Messenger",
        adapter_factory=MSNPlatformAdapter,
        check_fn=check_requirements, validate_config=validate_config,
        env_enablement_fn=_env_enablement,
        required_env=["HERMES_MSN_BRIDGE_TOKEN", "HERMES_MSN_OWNER_EMAIL"],
        allowed_users_env="HERMES_MSN_ALLOWED_USERS",
        allow_all_env="HERMES_MSN_ALLOW_ALL_USERS",
        max_message_length=4000,
        platform_hint="You are speaking to the owner via classic MSN Messenger. Send plain text, avoid Markdown formatting.",
        emoji="💬",
    )
