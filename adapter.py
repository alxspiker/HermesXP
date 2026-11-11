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

_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,79}\Z")
_FILE_BLOCKED = re.compile(
    r"(?:^|\.)(exe|bat|cmd|com|scr|pif|vbs|vbe|js|jse|wsf|wsh|msi|dll|lnk|ps1|hta|cpl|msc|jar|gadget)(?:\.|\Z)",
    re.IGNORECASE)
_FILE_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])\Z", re.IGNORECASE)
_FILE_SHA = re.compile(r"^[0-9a-f]{64}\Z")
MAX_MSN_FILE_BYTES = 8388608


def safe_file_basename(name):
    if not isinstance(name, str) or not _FILE_NAME.match(name):
        return None
    if _FILE_RESERVED.match(name.split(".", 1)[0]):
        return None
    if _FILE_BLOCKED.search(name):
        return None
    return name


class InboundDedupLedger:
    """Private, bounded ledger of inbound bridge IDs already accepted by Hermes."""

    MAX_IDS = 256
    MAX_BYTES = 32768

    def __init__(self, path):
        self.path = Path(path)

    def contains(self, message_id):
        return message_id in self._read()

    def remember(self, message_id):
        if not isinstance(message_id, str) or not message_id or len(message_id) > 128:
            raise ValueError("invalid inbound message id")
        ids = self._read()
        if message_id in ids:
            return False
        ids.append(message_id)
        self._write(ids[-self.MAX_IDS:])
        return True

    def _read(self):
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(self.MAX_BYTES + 1)
        except FileNotFoundError:
            return []
        if len(raw) > self.MAX_BYTES:
            raise ValueError("inbound ledger too large")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("ids"), list):
            raise ValueError("invalid inbound ledger")
        ids = data["ids"]
        if len(ids) > self.MAX_IDS or not all(
                isinstance(item, str) and 0 < len(item) <= 128 for item in ids):
            raise ValueError("invalid inbound ledger ids")
        return ids

    def _write(self, ids):
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(json.dumps({"ids": ids}).encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
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
        self._pending_outbound_acks = {}
        self._queue_flush_task = None
        self._queue_flush_event = asyncio.Event()
        queue_path = os.environ.get("HERMES_MSN_OFFLINE_QUEUE", "").strip()
        if not queue_path:
            queue_path = str(Path.home() / ".hermes" / "hermesxp-gateway-offline-queue.json")
        self.offline_queue = OfflineOutboundQueue(queue_path)
        ledger_path = Path(queue_path).with_name(Path(queue_path).stem + ".inbound-seen.json")
        self.inbound_ledger = InboundDedupLedger(ledger_path)
        self._reliable_queue = False

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
            reliable_queue = request.get("protocol") == "queue-ack-v1"
            self._reliable_queue = reliable_queue
            self.bridge_writer = writer
            hello_ok = {"type": "hello_ok"}
            if reliable_queue:
                hello_ok["protocol"] = "queue-ack-v1"
            writer.write(json.dumps(hello_ok).encode("utf-8") + bytes([10]))
            await writer.drain()
            log.info("Local MSN bridge connected")
            if self._queue_flush_task and not self._queue_flush_task.done():
                self._queue_flush_task.cancel()
            self._queue_flush_event.set()
            self._queue_flush_task = asyncio.create_task(self._flush_offline_queue())
            while True:
                data = await reader.readline()
                if not data:
                    break
                try:
                    msg = json.loads(data)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "send_ack":
                    message_id = msg.get("id")
                    if not isinstance(message_id, str):
                        continue
                    pending = self._pending_outbound_acks.get(message_id)
                    if msg.get("status") == "accepted_by_bridge" and pending and not pending.done():
                        pending.set_result(True)
                    continue
                if msg.get("type") == "incoming_file":
                    if any(key in msg for key in ("contents", "body", "text", "path")):
                        continue
                    sender = str(msg.get("sender", "")).lower().strip()
                    name = safe_file_basename(msg.get("name"))
                    size = msg.get("size")
                    digest = msg.get("sha256")
                    if (sender != self.owner or name is None or type(size) is not int or
                            size < 1 or size > MAX_MSN_FILE_BYTES or
                            not isinstance(digest, str) or not _FILE_SHA.match(digest)):
                        continue
                    notice = f"[file received] {name} ({size} bytes, sha256 {digest})"
                    event = MessageEvent(
                        text=notice,
                        message_type=MessageType.TEXT,
                        user_id=sender,
                        user_name=sender,
                        message_id=str(uuid.uuid4()),
                        source=SessionSource(platform=Platform("hermes_msn"), chat_id=sender,
                                             chat_type="dm", user_id=sender, user_name=sender),
                    )
                    await self.handle_message(event)
                    continue
                if msg.get("type") != "incoming":
                    continue
                message_id = msg.get("id")
                if reliable_queue and (
                        not isinstance(message_id, str) or not message_id or len(message_id) > 128):
                    continue
                sender = str(msg.get("sender", "")).lower().strip()
                body = msg.get("body", "")
                # Fail closed: even other contacts on Escargot must never trigger tools.
                if sender != self.owner or not isinstance(body, str) or not body.strip():
                    if reliable_queue:
                        try:
                            self.inbound_ledger.remember(message_id)
                            await self._ack_incoming(writer, message_id)
                        except (OSError, ValueError) as err:
                            log.warning("MSN inbound reject not durably recorded: %s", type(err).__name__)
                    continue
                body = body[:4000]
                if reliable_queue:
                    try:
                        if self.inbound_ledger.contains(message_id):
                            await self._ack_incoming(writer, message_id)
                            continue
                    except (OSError, ValueError) as err:
                        log.warning("MSN inbound dedup ledger unreadable: %s", type(err).__name__)
                        continue
                event = MessageEvent(
                    text=body,
                    message_type=MessageType.TEXT,
                    user_id=sender,
                    user_name=sender,
                    message_id=message_id if reliable_queue else str(uuid.uuid4()),
                    source=SessionSource(platform=Platform("hermes_msn"), chat_id=sender,
                                         chat_type="dm", user_id=sender, user_name=sender),
                )
                await self.handle_message(event)
                if reliable_queue:
                    try:
                        self.inbound_ledger.remember(message_id)
                        await self._ack_incoming(writer, message_id)
                    except (OSError, ValueError) as err:
                        log.warning("MSN inbound acknowledgement not durable: %s", type(err).__name__)
        except (ValueError, UnicodeDecodeError, OSError, asyncio.IncompleteReadError) as err:
            log.warning("MSN bridge error: %s", err)
        finally:
            flush_task = self._queue_flush_task
            self._queue_flush_task = None
            if flush_task and flush_task is not asyncio.current_task() and not flush_task.done():
                flush_task.cancel()
                await asyncio.gather(flush_task, return_exceptions=True)
            for acknowledgement in self._pending_outbound_acks.values():
                if not acknowledgement.done():
                    acknowledgement.cancel()
            self._pending_outbound_acks.clear()
            if authorized and writer is self.bridge_writer:
                self.bridge_writer = None
                self._reliable_queue = False
            self._bridge_tasks.discard(task)
            writer.close()
            await writer.wait_closed()

    async def _ack_incoming(self, writer, message_id):
        writer.write(json.dumps({
            "type": "incoming_ack", "id": message_id,
        }).encode("utf-8") + bytes([10]))
        await writer.drain()

    def _write_send(self, writer, chat_id, text, message_id=None):
        packet = {"type": "send", "to": chat_id, "text": text}
        if message_id is not None:
            packet["id"] = message_id
        writer.write(json.dumps(packet, ensure_ascii=False).encode("utf-8") + bytes([10]))

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
        while True:
            async with self._write_lock:
                try:
                    pending = self.offline_queue.pending()
                except (OSError, ValueError):
                    log.warning("MSN offline queue unreadable; not flushing")
                    return
                if not pending:
                    self._queue_flush_event.clear()
            if not pending:
                await self._queue_flush_event.wait()
                continue
            item = pending[0]
            writer = self.bridge_writer
            if writer is None or writer.is_closing():
                return
            acknowledgement = asyncio.get_running_loop().create_future()
            self._pending_outbound_acks[item["id"]] = acknowledgement
            try:
                async with self._write_lock:
                    if writer is not self.bridge_writer or writer.is_closing():
                        return
                    self._write_send(
                        writer, item["to"], item["text"],
                        item["id"] if self._reliable_queue else None,
                    )
                    await writer.drain()
                if self._reliable_queue:
                    await asyncio.wait_for(acknowledgement, timeout=3.0)
                else:
                    log.warning("MSN legacy bridge has no durable ACK; handing off queued text")
            except asyncio.TimeoutError:
                await asyncio.sleep(0.5)
                continue
            except OSError:
                return
            finally:
                self._pending_outbound_acks.pop(item["id"], None)
            try:
                self.offline_queue.ack(item["id"])
            except (OSError, ValueError):
                return

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        chat_id = str(chat_id).strip().lower()
        if chat_id != self.owner:
            return SendResult(success=False, error="Recipient not authorized")
        async with self._write_lock:
            file_name = metadata.get("file") if isinstance(metadata, dict) else None
            writer = self.bridge_writer
            if file_name is None:
                offline = not writer or writer.is_closing()
                queued = self._queue_offline(chat_id, str(content)[:4000])
                if not queued.success:
                    return queued
                queued.raw_response = {
                    "queued": True,
                    "offline": offline,
                    "status": "queued",
                }
                if not offline:
                    self._queue_flush_event.set()
                    if self._queue_flush_task is None or self._queue_flush_task.done():
                        self._queue_flush_task = asyncio.create_task(self._flush_offline_queue())
                return queued
            if not writer or writer.is_closing():
                return SendResult(success=False, error="MSN bridge is offline", retryable=True)
            safe = safe_file_basename(file_name)
            if safe is None:
                return SendResult(success=False, error="MSN file name is not an outbox basename")
            packet = {"type": "send_file", "to": chat_id, "name": safe}
            try:
                writer.write(json.dumps(packet, ensure_ascii=False).encode("utf-8") + bytes([10]))
                await writer.drain()
                return SendResult(success=True, message_id=str(uuid.uuid4()))
            except OSError as err:
                return SendResult(success=False, error=str(err), retryable=True)

    async def get_chat_info(self, chat_id):
        return {"name": str(chat_id), "type": "dm"}

    async def disconnect(self):
        writer = self.bridge_writer
        self.bridge_writer = None
        self._reliable_queue = False
        if writer:
            writer.close()
        tasks = list(self._bridge_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._queue_flush_task and not self._queue_flush_task.done():
            self._queue_flush_task.cancel()
            await asyncio.gather(self._queue_flush_task, return_exceptions=True)
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
    extra = getattr(config, "extra", None)
    token = str(extra_or_secret(extra, "token", "HERMES_MSN_BRIDGE_TOKEN") or "")
    owner = str(extra_or_secret(extra, "owner_email", "HERMES_MSN_OWNER_EMAIL") or "").strip().lower()
    if len(token) < 32 or not owner or chat_id.strip().lower() != owner:
        return {"error": "MSN recipient not authorized or bridge not configured"}
    message_id = str(uuid.uuid4())
    route = "/send"
    if media_files:
        if not isinstance(media_files, (list, tuple)) or len(media_files) != 1:
            return {"error": "MSN file send accepts one outbox basename"}
        name = safe_file_basename(media_files[0])
        if name is None:
            return {"error": "MSN files must be outbox basenames"}
        payload = json.dumps({"to": owner, "name": name}, ensure_ascii=False).encode("utf-8")
        route = "/file/send"
    else:
        if force_document:
            return {"error": "MSN standalone sender supports text only"}
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            return {"error": "MSN message must be 1–4000 characters"}
        payload = json.dumps({
            "to": owner, "text": message, "id": message_id,
        }, ensure_ascii=False).encode("utf-8")
        if len(payload) > 8192:
            return {"error": "MSN message too large"}

    def _post():
        conn = http.client.HTTPConnection("127.0.0.1", 18769, timeout=8)
        try:
            conn.request("POST", route, body=payload,
                         headers={"X-Hermes-Token": token, "Content-Type": "application/json"})
            response = conn.getresponse()
            data = response.read(512)
            if response.status != 202:
                return {"error": f"MSN bridge rejected send (HTTP {response.status})"}
            result = json.loads(data)
            if not result.get("success"):
                return {"error": "MSN bridge did not accept the send"}
            if route == "/send":
                response_id = result.get("message_id")
                if not isinstance(response_id, str) or not response_id:
                    response_id = message_id
                status = result.get("status")
                if status not in ("queued", "accepted_by_bridge"):
                    status = "queued" if result.get("offline") is True else "submitted"
                return {
                    "success": True,
                    "message_id": response_id,
                    "queued": bool(result.get("queued", True)),
                    "offline": result.get("offline") is True,
                    "status": status,
                    "delivered": False,
                }
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
        # XP diagnostics, screen capture and bounded controls are native
        # Hermes tools. They never require a browser dashboard or host API.
        # The XP client is selected only from the private pairing registry.
        xp_tools = (
            (
                "xp_status", "Read HermesXP host services, update state and paired XP devices. "
                "Optional probe contacts each XP device read-only.",
                {"probe": {"type": "boolean", "description": "Probe paired XP devices live (default false)"}},
                "🖥️",
            ),
            (
                "xp_screen", "Capture a paired XP desktop to a private host file, with optional "
                "on-demand analysis by the user's configured vision model.",
                {
                    "device": {"type": "string", "description": "Exact paired XP device name; optional if one device"},
                    "save": {"type": "boolean", "description": "Save private screenshot on Hermes host (default true)"},
                    "analyze": {"type": "boolean", "description": "Run configured vision model (default false)"},
                },
                "📸",
            ),
            (
                "xp_control", "Perform one bounded authenticated XP desktop action. "
                "Requires host HERMES_CUA_LIVE_ENABLED=1 and confirm_live=true. No arbitrary shell commands.",
                {
                    "device": {"type": "string", "description": "Exact paired XP device name; optional if one device"},
                    "action": {"type": "string", "enum": ["click", "right_click", "double_click",
                                                             "drag", "scroll", "type_text", "key_press"]},
                    "coords": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "end_coords": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "delta": {"type": "integer", "minimum": -5, "maximum": 5},
                    "text": {"type": "string", "maxLength": 128},
                    "confirm_live": {"type": "boolean", "description": "Explicit confirmation for a live action"},
                },
                "🖱️",
            ),
            (
                "xp_service", "Read or manage a named Windows XP service via the authenticated "
                "Service Control Manager interface. Writes require host opt-in and confirmation.",
                {
                    "device": {"type": "string", "description": "Exact paired XP device name; optional if one device"},
                    "name": {"type": "string", "maxLength": 80, "description": "Windows service name, not a command"},
                    "action": {"type": "string", "enum": ["status", "start", "stop", "restart"]},
                    "confirm_live": {"type": "boolean", "description": "Required for start/stop/restart"},
                },
                "⚙️",
            ),
        )
        for name, description, properties, emoji in xp_tools:
            required = ["action"] if name == "xp_control" else ["name"] if name == "xp_service" else []
            register_tool(
                name=name, toolset="hermes-msn",
                schema={
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object", "properties": properties,
                        "required": required, "additionalProperties": False,
                    },
                },
                handler=lambda args, operation=name, **_kwargs: _handle_xp_tool(operation, args),
                check_fn=lambda: True,
                emoji=emoji,
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


def _handle_xp_tool(operation, args):
    """Load isolated XP helpers without shadowing Hermes' own tools package.

    Hermes already imports a top-level tools Python package. Adding the
    plugin root to sys.path does not fix that package's __path__, so use an
    isolated package namespace rooted at the plugin instead.
    """
    import hashlib
    import importlib.machinery
    import importlib.util
    import sys
    import types
    try:
        source = Path(__file__).resolve().parent
        root = next(
            parent for parent in (source, *list(source.parents)[:3])
            if (parent / "tools/xp_agent_tools.py").is_file()
        )
        path = root / "tools/xp_agent_tools.py"
        name = "_hermesxp_native_" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
        if name not in sys.modules:
            package = types.ModuleType(name)
            package.__path__ = [str(root / "tools")]
            package.__package__ = name
            package.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
            sys.modules[name] = package
        child = name + ".xp_agent_tools"
        module = sys.modules.get(child)
        stamp = path.stat().st_mtime_ns
        if module is None or getattr(module, "_hermesxp_stamp", None) != stamp:
            spec = importlib.util.spec_from_file_location(child, path)
            if spec is None or spec.loader is None:
                raise ImportError("HermesXP native tools cannot be loaded")
            module = importlib.util.module_from_spec(spec)
            sys.modules[child] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(child, None)
                raise
            module._hermesxp_stamp = stamp
        return module.invoke(operation, args)
    except (ImportError, OSError, ValueError, StopIteration) as exc:
        log.warning("HermesXP agent tool unavailable: %s", type(exc).__name__)
        return json.dumps({"success": False, "error": "HermesXP paired-device tools unavailable"})


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
