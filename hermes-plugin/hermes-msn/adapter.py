"""Hermes XP/MSN platform adapter.

Local JSON-lines bridge: 127.0.0.1:18764 (authentication with a random token).
Optional LAN-only XP connection probe: configurable bind IP:18765, *no secrets*.

Designed for Hermes' documented platform plugin API; not a standalone service.
"""
import asyncio
import http.client
import hmac
import json
import logging
import importlib.util
import os
from pathlib import Path
import re
import socket
import time
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


class OfflineOutboundQueue:
    """Host-local FIFO of texts not yet handed to the MSN bridge.

    A corrupt file is never rewritten. Callers must treat a read error as
    "do not claim this text was stored."
    """

    MAX_ITEMS = 64

    def __init__(self, path):
        self.path = Path(path)

    def pending(self):
        return self._read()

    def enqueue(self, to, text):
        try:
            items = self._read()
        except (OSError, ValueError) as err:
            log.warning("MSN offline queue unreadable: %s", type(err).__name__)
            return {"ok": False, "error": "offline queue unreadable"}
        if len(items) >= self.MAX_ITEMS:
            return {"ok": False, "error": "offline queue full"}
        item = {
            "id": str(uuid.uuid4()),
            "to": to,
            "text": text,
            "queued_at": time.time(),
        }
        items.append(item)
        try:
            self._write(items)
        except OSError as err:
            log.warning("MSN offline queue write failed: %s", type(err).__name__)
            return {"ok": False, "error": "offline queue unreadable"}
        return {"ok": True, "id": item["id"]}

    def ack(self, message_id):
        items = [item for item in self._read() if item.get("id") != message_id]
        self._write(items)

    def _read(self):
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("invalid queue")
        for item in data["items"]:
            if not isinstance(item, dict):
                raise ValueError("invalid item")
            if not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError("invalid id")
            if not isinstance(item.get("to"), str) or not isinstance(item.get("text"), str):
                raise ValueError("invalid payload")
            if not isinstance(item.get("queued_at"), (int, float)):
                raise ValueError("invalid timestamp")
        return data["items"]

    def _write(self, items):
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        payload = json.dumps({"items": items}, ensure_ascii=False).encode("utf-8")
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)


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
        queue_path = os.environ.get("HERMES_MSN_OFFLINE_QUEUE", "").strip()
        if not queue_path:
            queue_path = str(Path.home() / ".hermes" / "hermesxp-gateway-offline-queue.json")
        self.offline_queue = OfflineOutboundQueue(queue_path)

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        if len(self.secret) < 32 or not self.owner or "@" not in self.owner:
            log.error("MSN bridge secret must be >=32 chars and owner address must be configured")
            return False
        # Local MSN server health check: the bridge talks to the server named
        # by MSN_SERVER_HOST (installer default 127.0.0.1). When that is a
        # local address, verify the NS port answers before binding the bridge
        # port, so a down server is a clear log line, not a silent
        # no-message state. An external host (Escargot mode) skips the probe.
        msn_host = (os.environ.get("MSN_SERVER_HOST", "127.0.0.1") or "127.0.0.1").strip()
        if msn_host in ("127.0.0.1", "localhost", "::1"):
            try:
                with socket.create_connection((msn_host, 1863), timeout=2):
                    pass
            except OSError:
                log.error("Local MSN server is not reachable on %s:1863 — start the msn-server service (local-server/install.sh) before enabling this platform", msn_host)
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
            await self._flush_offline_queue()
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

    def _write_send(self, writer, chat_id, text):
        writer.write((json.dumps(
            {"type": "send", "to": chat_id, "text": text},
            ensure_ascii=False) + "\n").encode("utf-8"))

    def _queue_offline(self, chat_id, text):
        queued = self.offline_queue.enqueue(chat_id, text)
        if not queued["ok"]:
            return SendResult(
                success=False,
                error=queued["error"],
                retryable=queued["error"] == "offline queue full",
            )
        return SendResult(
            success=True,
            message_id=queued["id"],
            raw_response={"queued": True, "offline": True},
            retryable=False,
        )

    async def _flush_offline_queue(self):
        async with self._write_lock:
            try:
                pending = self.offline_queue.pending()
            except (OSError, ValueError):
                log.warning("MSN offline queue unreadable; not flushing")
                return
            for item in pending:
                writer = self.bridge_writer
                if writer is None or writer.is_closing():
                    return
                try:
                    self._write_send(writer, item["to"], item["text"])
                    await writer.drain()
                except OSError:
                    return
                try:
                    self.offline_queue.ack(item["id"])
                except (OSError, ValueError):
                    return

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        chat_id = str(chat_id).strip().lower()
        if chat_id != self.owner:
            return SendResult(success=False, error="Recipient not authorized")
        text = str(content)[:4000]
        async with self._write_lock:
            writer = self.bridge_writer
            if writer is None or writer.is_closing():
                return self._queue_offline(chat_id, text)
            try:
                self._write_send(writer, chat_id, text)
                await writer.drain()
                return SendResult(success=True, message_id=str(uuid.uuid4()))
            except OSError as err:
                queued = self._queue_offline(chat_id, text)
                if queued.success:
                    return queued
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


async def standalone_send(config, chat_id, message, *, thread_id=None,
                          media_files=None, force_document=False):
    """Out-of-process Hermes send_message delivery via the local MSN bridge.

    A cron/terminal CLI call doesn't share the gateway runner's Python
    adapter registry. The Node bridge already owns the authenticated MSN
    session, so it exposes a token-protected *loopback only* send endpoint.
    This never contacts XP directly and never sends to arbitrary recipients.
    """
    if media_files or force_document:
        return {"error": "MSN standalone sender supports text only"}
    extra = getattr(config, "extra", None)
    token = str(extra_or_secret(extra, "token", "HERMES_MSN_BRIDGE_TOKEN") or "")
    owner = str(extra_or_secret(extra, "owner_email", "HERMES_MSN_OWNER_EMAIL") or "").strip().lower()
    if len(token) < 32 or not owner or chat_id.strip().lower() != owner:
        return {"error": "MSN recipient not authorized or bridge not configured"}
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        return {"error": "MSN message must be 1–4000 characters"}
    payload = json.dumps({"to": owner, "text": message}, ensure_ascii=False).encode("utf-8")
    if len(payload) > 8192:
        return {"error": "MSN message too large"}

    def _post():
        conn = http.client.HTTPConnection("127.0.0.1", 18769, timeout=8)
        try:
            conn.request("POST", "/send", body=payload,
                         headers={"X-Hermes-Token": token, "Content-Type": "application/json"})
            response = conn.getresponse()
            data = response.read(512)
            if response.status != 202:
                return {"error": f"MSN bridge rejected send (HTTP {response.status})"}
            result = json.loads(data)
            if not result.get("success"):
                return {"error": "MSN bridge did not accept the send"}
            # The bridge queues a send via the MSN library; not an end-to-end
            # acknowledgement of delivery to Windows Live Messenger.
            return {"success": True, "message_id": str(uuid.uuid4()), "queued": True}
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_post)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        log.warning("MSN standalone bridge request failed: %s", type(exc).__name__)
        return {"error": "MSN bridge sender unavailable on localhost"}


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
        standalone_sender_fn=standalone_send,
        platform_hint="You are speaking to the owner via classic MSN Messenger. Send plain text, avoid Markdown formatting.",
        emoji="💬",
    )
    # Hermes has explicit native MSN call control just like send_message:
    # the tool goes to the already signed-in local bridge, never to XP or
    # an arbitrary contact. Existing /nativecall and /hangup chat commands
    # remain supported independently.
    register_tool = getattr(ctx, "register_tool", None)
    if callable(register_tool):
        register_tool(
            name="msn_call", toolset="hermes-msn",
            schema={
                "name": "msn_call",
                "description": (
                    "Control an authenticated native Windows Live Messenger voice "
                    "call with the paired owner. Start, end or check the call; "
                    "the audio and Hermes tools are handled by the Hermes Talk plugin."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["start", "end", "status"],
                                   "description": "Start an outgoing MSN call, end the current call, or read call status."},
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            },
            handler=_handle_msn_call,
            check_fn=check_requirements,
            emoji="📞",
        )
    # Run Hermes Talk in the same Hermes CLI plugin context so its provider,
    # OAuth, tool delegation, and model choices stay with the Talk plugin.
    register_cli = getattr(ctx, "register_cli_command", None)
    if callable(register_cli):
        register_cli(
            name="xpvoice", help="HermesXP MSN <-> Hermes Talk audio service",
            setup_fn=_setup_xpvoice_cli, handler_fn=_run_xpvoice_cli,
            description="Authenticated loopback PCM bridge using the selected Hermes Talk provider",
        )


def _handle_msn_call(args, **_kwargs):
    """Hermes agent tool for native MSN call control. Not a shell shortcut."""
    action = args.get("action") if isinstance(args, dict) else None
    if action not in ("start", "end", "status"):
        return json.dumps({"success": False, "error": "Invalid call action"})
    token = str(get_scoped_secret("HERMES_MSN_BRIDGE_TOKEN") or "")
    owner = str(get_scoped_secret("HERMES_MSN_OWNER_EMAIL") or "").strip().lower()
    if len(token) < 32 or not owner:
        return json.dumps({"success": False, "error": "MSN bridge is not configured"})
    endpoint = "/call/" + action
    try:
        connection = http.client.HTTPConnection("127.0.0.1", 18769, timeout=6)
        try:
            connection.request("POST", endpoint, body=b"",
                               headers={"X-Hermes-Token": token, "Content-Length": "0"})
            response = connection.getresponse()
            payload = json.loads(response.read(1024))
            if response.status not in (200, 202):
                return json.dumps({"success": False,
                                   "error": payload.get("error", "Call action unavailable")})
            return json.dumps(payload)
        finally:
            connection.close()
    except (OSError, ValueError, http.client.HTTPException):
        return json.dumps({"success": False, "error": "Local MSN call controller unavailable"})


def _talk_bridge():
    source = Path(__file__).resolve().parent / "tools" / "talk_bridge.py"
    if not source.is_file():
        raise RuntimeError("HermesXP full plugin checkout required for Talk audio")
    spec = importlib.util.spec_from_file_location("hermesxp_talk_bridge", source)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _setup_xpvoice_cli(parser):
    _talk_bridge().setup_cli(parser)


def _run_xpvoice_cli(args):
    _talk_bridge().cli_entry(args)
