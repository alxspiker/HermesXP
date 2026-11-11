"""Offline message queue. Host-side only; no XP machine and no live bridge ports.

The break each test names is a production change that would lose, duplicate,
reorder, or leak an owner message. Expectations are literals, not helpers
from the code under test.
"""
import asyncio
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

TESTS = pathlib.Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))
from test_adapter import load_adapter


class TestAdapterOfflineQueue(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.queue_path = pathlib.Path(self.tmp.name) / "gateway-queue.json"
        os.environ["HERMES_MSN_OFFLINE_QUEUE"] = str(self.queue_path)
        os.environ.pop("HERMES_XP_PROBE_BIND", None)
        self.m = load_adapter()
        self.m.BRIDGE_PORT = 0
        self.adapter = self.m.MSNPlatformAdapter(self.m.PlatformConfig({
            "token": "S" * 48,
            "owner_email": "me@example.invalid",
        }))
        with patch.object(self.m.socket, "create_connection"):
            self.assertTrue(await self.adapter.connect())
        self.bridge_port = self.adapter.bridge_server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        await self.adapter.disconnect()
        os.environ.pop("HERMES_MSN_OFFLINE_QUEUE", None)
        self.tmp.cleanup()

    async def _hello(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.bridge_port)
        writer.write(json.dumps({
            "type": "hello", "token": "S" * 48,
            "protocol": "queue-ack-v1",
        }).encode() + bytes([10]))
        await writer.drain()
        self.assertEqual(json.loads(await reader.readline()), {
            "type": "hello_ok", "protocol": "queue-ack-v1",
        })
        return reader, writer

    async def _wait_until_bridge_gone(self):
        for _ in range(50):
            if self.adapter.bridge_writer is None:
                return
            await asyncio.sleep(0.01)
        self.fail("bridge writer was not cleared after disconnect")

    async def _receive_and_ack(self, reader, writer, count):
        packets = []
        for _ in range(count):
            packet = json.loads(await asyncio.wait_for(reader.readline(), 2))
            packets.append(packet)
            writer.write((json.dumps({
                "type": "send_ack", "id": packet["id"],
                "status": "accepted_by_bridge",
            }) + chr(10)).encode())
            await writer.drain()
        return packets

    async def _wait_for_queue_empty(self):
        for _ in range(50):
            stored = json.loads(self.queue_path.read_text(encoding="utf-8"))
            if not stored["items"]:
                return
            await asyncio.sleep(0.01)
        self.fail("offline queue was not cleared after bridge ACKs")

    async def test_inbound_replay_is_acked_once_across_gateway_restart(self):
        reader, writer = await self._hello()
        message = {
            "type": "incoming", "id": "bridge-inbound-0001",
            "sender": "me@example.invalid", "body": "hello once",
        }
        for _ in range(2):
            writer.write(json.dumps(message).encode() + bytes([10]))
            await writer.drain()
            self.assertEqual(json.loads(await asyncio.wait_for(reader.readline(), 2)), {
                "type": "incoming_ack", "id": message["id"],
            })
        for _ in range(50):
            if self.adapter.messages:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(len(self.adapter.messages), 1)
        self.assertEqual(self.adapter.messages[0].message_id, message["id"])
        ledger_path = self.queue_path.with_name("gateway-queue.inbound-seen.json")
        self.assertTrue(ledger_path.exists())
        self.assertEqual(ledger_path.stat().st_mode & 0o777, 0o600)
        writer.close()
        await writer.wait_closed()
        await self._wait_until_bridge_gone()
        await self.adapter.disconnect()

        self.m = load_adapter()
        self.m.BRIDGE_PORT = 0
        self.adapter = self.m.MSNPlatformAdapter(self.m.PlatformConfig({
            "token": "S" * 48,
            "owner_email": "me@example.invalid",
        }))
        with patch.object(self.m.socket, "create_connection"):
            self.assertTrue(await self.adapter.connect())
        self.bridge_port = self.adapter.bridge_server.sockets[0].getsockname()[1]
        reader, writer = await self._hello()
        writer.write(json.dumps(message).encode() + bytes([10]))
        await writer.drain()
        self.assertEqual(json.loads(await asyncio.wait_for(reader.readline(), 2)), {
            "type": "incoming_ack", "id": message["id"],
        })
        await asyncio.sleep(0.05)
        self.assertEqual(self.adapter.messages, [])
        writer.close()
        await writer.wait_closed()

    async def test_offline_sends_persist_and_push_in_order_on_reconnect(self):
        # Break: dropping the body while the bridge socket is down, pushing
        # out of order, or leaving an acked item to be sent again.
        first = await self.adapter.send("me@example.invalid", "one")
        second = await self.adapter.send("Me@Example.invalid", "two")
        self.assertTrue(first.success, getattr(first, "error", None))
        self.assertTrue(second.success, getattr(second, "error", None))
        self.assertFalse(first.retryable)
        self.assertEqual(first.raw_response, {
            "queued": True, "offline": True, "status": "queued",
        })
        self.assertNotEqual(first.message_id, second.message_id)
        stored = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual([item["text"] for item in stored["items"]], ["one", "two"])
        self.assertEqual(
            [item["to"] for item in stored["items"]],
            ["me@example.invalid", "me@example.invalid"],
        )
        self.assertNotIn("S" * 48, self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual(self.queue_path.stat().st_mode & 0o777, 0o600)

        reader, writer = await self._hello()
        pushed = await self._receive_and_ack(reader, writer, 2)
        self.assertEqual([item["type"] for item in pushed], ["send", "send"])
        self.assertEqual([item["text"] for item in pushed], ["one", "two"])
        await self._wait_for_queue_empty()
        self.assertEqual(
            [item["to"] for item in pushed],
            ["me@example.invalid", "me@example.invalid"],
        )
        self.assertEqual(json.loads(self.queue_path.read_text(encoding="utf-8"))["items"], [])

        writer.close()
        await writer.wait_closed()
        await self._wait_until_bridge_gone()
        third = await self.adapter.send("me@example.invalid", "three")
        self.assertTrue(third.success, getattr(third, "error", None))
        self.assertEqual(third.raw_response, {
            "queued": True, "offline": True, "status": "queued",
        })
        reader, writer = await self._hello()
        again = (await self._receive_and_ack(reader, writer, 1))[0]
        self.assertEqual(again["text"], "three")
        await self._wait_for_queue_empty()
        self.assertEqual(json.loads(self.queue_path.read_text(encoding="utf-8"))["items"], [])
        writer.close()
        await writer.wait_closed()

    async def test_online_text_is_persisted_until_bridge_ack(self):
        reader, writer = await self._hello()
        result = await self.adapter.send("me@example.invalid", "live")
        self.assertTrue(result.success, getattr(result, "error", None))
        self.assertEqual(result.raw_response, {
            "queued": True, "offline": False, "status": "queued",
        })
        payload = json.loads(await asyncio.wait_for(reader.readline(), 2))
        self.assertEqual(payload["id"], result.message_id)
        self.assertEqual(payload["text"], "live")
        stored = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in stored["items"]], [result.message_id])
        writer.write((json.dumps({
            "type": "send_ack", "id": result.message_id,
            "status": "accepted_by_bridge",
        }) + chr(10)).encode())
        await writer.drain()
        await self._wait_for_queue_empty()
        writer.close()
        await writer.wait_closed()

    async def test_outbound_queue_waits_for_durable_bridge_ack(self):
        result = await self.adapter.send("me@example.invalid", "wait-for-ack")
        self.assertTrue(result.success, getattr(result, "error", None))
        message_id = result.message_id
        reader, writer = await self._hello()
        packet = json.loads(await asyncio.wait_for(reader.readline(), 2))
        self.assertEqual(packet["id"], message_id)
        stored = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in stored["items"]], [message_id])
        writer.write((json.dumps({
            "type": "send_ack", "id": message_id,
            "status": "accepted_by_bridge",
        }) + chr(10)).encode())
        await writer.drain()
        for _ in range(50):
            stored = json.loads(self.queue_path.read_text(encoding="utf-8"))
            if not stored["items"]:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(stored["items"], [])
        writer.close()
        await writer.wait_closed()

    async def test_full_offline_queue_rejects_new_text_and_keeps_earlier_order(self):
        # Break: accepting a 65th text, or dropping the first so the new one fits.
        for index in range(64):
            result = await self.adapter.send("me@example.invalid", f"m{index}")
            self.assertTrue(result.success, getattr(result, "error", None))
        rejected = await self.adapter.send("me@example.invalid", "overflow")
        self.assertFalse(rejected.success)
        self.assertEqual(rejected.error, "offline queue full")
        self.assertTrue(rejected.retryable)
        stored = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual([item["text"] for item in stored["items"]], [f"m{index}" for index in range(64)])
        self.assertNotIn("overflow", self.queue_path.read_text(encoding="utf-8"))

        reader, writer = await self._hello()
        pushed = await self._receive_and_ack(reader, writer, 64)
        pushed = [item["text"] for item in pushed]
        self.assertEqual(pushed, [f"m{index}" for index in range(64)])
        await self._wait_for_queue_empty()
        self.assertEqual(json.loads(self.queue_path.read_text(encoding="utf-8"))["items"], [])
        writer.close()
        await writer.wait_closed()

    async def test_unauthorized_recipient_is_not_queued(self):
        # Break: persisting a text addressed to someone other than the owner.
        result = await self.adapter.send("stranger@example.invalid", "nope")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Recipient not authorized")
        self.assertFalse(self.queue_path.exists())

    async def test_corrupt_queue_file_is_not_replaced(self):
        # Break: a later send truncating or rewriting a queue file we cannot parse.
        self.queue_path.write_text("{not-json", encoding="utf-8")
        before = self.queue_path.read_bytes()
        result = await self.adapter.send("me@example.invalid", "keep-the-file")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "offline queue unreadable")
        self.assertFalse(result.retryable)
        self.assertEqual(self.queue_path.read_bytes(), before)

    async def test_overlong_text_is_stored_truncated_to_4000(self):
        # Break: persisting or pushing more than the live send path would have written.
        body = "x" * 4001
        result = await self.adapter.send("me@example.invalid", body)
        self.assertTrue(result.success, getattr(result, "error", None))
        stored = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["items"][0]["text"], "x" * 4000)


ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "msn-bridge" / "bridge.js"
QUEUE_JS = ROOT / "msn-bridge" / "offline_queue.js"


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def bridge_env(queue_path, gateway_port, standalone_port):
    env = dict(os.environ)
    env.pop("HERMES_MSN_NATIVE_CALL", None)
    env.update({
        "MSN_BOT_EMAIL": "bot@example.invalid",
        "MSN_BOT_PASSWORD": "test",
        "HERMES_MSN_OWNER_EMAIL": "owner@example.invalid",
        "HERMES_MSN_BRIDGE_TOKEN": "z" * 32,
        "HERMES_MSN_STANDALONE_PORT": str(standalone_port),
        "HERMES_MSN_GATEWAY_PORT": str(gateway_port),
        "HERMES_MSN_BRIDGE_QUEUE": str(queue_path),
        "HERMES_MSN_TRANSFER_ROOT": str(pathlib.Path(queue_path).parent / "transfers"),
    })
    return env


class TestNodeOfflineQueue(unittest.TestCase):
    def test_queue_module_survives_reload_and_does_not_rewrite_corrupt_files(self):
        # Break: dropping a stored text across process restart, writing a
        # world-readable file, accepting a 65th outbound item, or replacing
        # a corrupt file with an empty queue.
        script = r"""
const fs = require('fs');
const os = require('os');
const path = require('path');
const q = require(process.argv[1]);
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hxq-'));
const file = path.join(dir, 'q.json');
let state = q.load(file);
const first = q.enqueueOutbound(state, {to:'owner@example.invalid', text:'one'});
const second = q.enqueueOutbound(state, {to:'owner@example.invalid', text:'two'});
q.save(file, state);
let loaded = q.load(file);
const mode = fs.statSync(file).mode & 0o777;
const roundTrip = first.ok && second.ok &&
  loaded.outbound.map(item => item.text).join(',') === 'one,two' &&
  mode === 0o600;
q.ack(loaded, 'outbound', first.item.id);
q.save(file, loaded);
loaded = q.load(file);
const acked = loaded.outbound.length === 1 && loaded.outbound[0].text === 'two';
const retryFile = path.join(dir, 'retry.json');
let retryState = q.load(retryFile);
const stableId = 'gateway-message-0001';
const original = q.enqueueOutbound(retryState, {
  id: stableId, to:'owner@example.invalid', text:'once',
});
q.save(retryFile, retryState);
retryState = q.load(retryFile);
const retry = q.enqueueOutbound(retryState, {
  id: stableId, to:'owner@example.invalid', text:'once',
});
const dedupPending = original.ok && retry.ok && retry.duplicate === true &&
  retryState.outbound.length === 1 && retry.item.id === stableId;
q.ack(retryState, 'outbound', stableId);
q.save(retryFile, retryState);
retryState = q.load(retryFile);
const afterAckRetry = q.enqueueOutbound(retryState, {
  id: stableId, to:'owner@example.invalid', text:'once',
});
const dedupAcked = afterAckRetry.ok && afterAckRetry.duplicate === true &&
  retryState.outbound.length === 0;
state = {outbound: [], inbound: []};
for (let i = 0; i < 64; i++) {
  q.enqueueOutbound(state, {to:'owner@example.invalid', text:'m' + i});
}
const overflow = q.enqueueOutbound(state, {to:'owner@example.invalid', text:'overflow'});
const capped = overflow.ok === false && state.outbound.length === 64 &&
  state.outbound[0].text === 'm0' && state.outbound[63].text === 'm63';
const inbound = q.enqueueInbound(state, {sender:'owner@example.invalid', body:'in'});
const keptInbound = inbound.ok && state.inbound.length === 1 &&
  state.inbound[0].body === 'in';
const inboundState = {outbound: [], inbound: []};
for (let i = 0; i < 64; i++) {
  q.enqueueInbound(inboundState, {sender:'owner@example.invalid', body:'i' + i});
}
const newest = q.enqueueInbound(inboundState, {sender:'owner@example.invalid', body:'newest'});
const inboundCap = newest.ok === false && newest.error === 'offline queue full' &&
  inboundState.inbound.length === 64 && inboundState.inbound[0].body === 'i0' &&
  inboundState.inbound[63].body === 'i63';
fs.writeFileSync(file, '{nope');
let threw = false;
try { q.load(file); } catch (err) { threw = true; }
const untouched = fs.readFileSync(file, 'utf8') === '{nope';
const ok = roundTrip && acked && dedupPending && dedupAcked &&
  capped && keptInbound && inboundCap && threw && untouched;
console.log(ok ? 'QUEUE_MODULE_PASS' : 'QUEUE_MODULE_FAIL');
process.exit(ok ? 0 : 1);
"""
        result = subprocess.run(
            ["node", "-e", script, str(QUEUE_JS)],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-400:] + result.stderr[-400:])
        self.assertIn("QUEUE_MODULE_PASS", result.stdout)

    def test_offline_standalone_send_is_pushed_in_order_when_msn_reconnects(self):
        # Break: calling sendMessage while the bot is signed out, dropping the
        # text, pushing it out of order, or returning success for a stranger.
        harness = r"""
const EventEmitter = require('events');
const Module = require('module');
const http = require('http');
const fs = require('fs');
const original = Module._load;
const sent = [];
class FakeClient extends EventEmitter {
  constructor(){ super(); this.active = false; }
  execute() {
    const timer = setInterval(() => {
      let queued;
      try { queued = JSON.parse(fs.readFileSync(process.env.HERMES_MSN_BRIDGE_QUEUE, 'utf8')); }
      catch (err) { return; }
      if (queued.outbound && queued.outbound.length >= 2) {
        clearInterval(timer);
        this.active = true;
        this.emit('msg', {type: 'connected'});
      }
    }, 20);
    timer.unref();
  }
  async sendMessage(to, text){ sent.push({to, text}); }
}
Module._load = function(request, ...args) {
  if (request === './msnclient/main.js') return {MSNClient: FakeClient};
  return original.call(this, request, ...args);
};
require(process.argv[1]);
function post(to, text) {
  return new Promise((resolve, reject) => {
    const bytes = Buffer.from(JSON.stringify({to, text}));
    const request = http.request({
      host: '127.0.0.1',
      port: Number(process.env.HERMES_MSN_STANDALONE_PORT),
      path: '/send', method: 'POST',
      headers: {'X-Hermes-Token': 'z'.repeat(32), 'Content-Length': bytes.length},
    }, response => {
      let body = '';
      response.on('data', chunk => body += chunk);
      response.on('end', () => {
        let parsed = {};
        try { parsed = JSON.parse(body); } catch (err) { parsed = {raw: body}; }
        resolve({code: response.statusCode, body: parsed});
      });
    });
    request.on('error', reject);
    request.end(bytes);
  });
}
setTimeout(async () => {
  try {
    const stranger = await post('stranger@example.invalid', 'nope');
    const first = await post('owner@example.invalid', 'one');
    const second = await post('Owner@Example.invalid', 'two');
    await new Promise(resolve => setTimeout(resolve, 80));
    const after = JSON.parse(fs.readFileSync(process.env.HERMES_MSN_BRIDGE_QUEUE, 'utf8'));
    const ok = stranger.code === 403 &&
      first.code === 202 && first.body.success === true && first.body.offline === true &&
      first.body.status === 'queued' && first.body.delivered === false &&
      second.code === 202 && second.body.offline === true &&
      second.body.status === 'queued' && second.body.delivered === false &&
      sent.map(item => item.text).join(',') === 'one,two' &&
      sent.every(item => item.to === 'owner@example.invalid') &&
      after.outbound.length === 0;
    console.log(JSON.stringify({
      ok, stranger: stranger.code, first, second, sent,
      remaining: after.outbound.length,
    }));
    process.exit(ok ? 0 : 8);
  } catch (err) {
    console.error(err);
    process.exit(9);
  }
}, 120);
"""
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = pathlib.Path(tmp) / "bridge-queue.json"
            env = bridge_env(queue_path, free_port(), free_port())
            result = subprocess.run(
                ["node", "-e", harness, str(BRIDGE)],
                env=env, capture_output=True, text=True, timeout=4,
            )
        self.assertEqual(result.returncode, 0, result.stdout[-500:] + result.stderr[-500:])
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["sent"], [
            {"to": "owner@example.invalid", "text": "one"},
            {"to": "owner@example.invalid", "text": "two"},
        ])

    def test_bridge_acknowledges_durable_outbound_ids_and_deduplicates_retries(self):
        harness = r"""
const EventEmitter = require('events');
const Module = require('module');
const original = Module._load;
class FakeClient extends EventEmitter {
  constructor(){ super(); this.active = false; }
  execute() {}
  async sendMessage() {}
}
Module._load = function(request, ...args) {
  if (request === './msnclient/main.js') return {MSNClient: FakeClient};
  return original.call(this, request, ...args);
};
require(process.argv[1]);
"""
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = pathlib.Path(tmp) / "bridge-queue.json"
            server = socket.socket()
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            server.settimeout(3)
            env = bridge_env(queue_path, server.getsockname()[1], free_port())
            proc = subprocess.Popen(
                ["node", "-e", harness, str(BRIDGE)],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            conn = None
            try:
                conn, _ = server.accept()
                conn.settimeout(3)

                newline = bytes([10])

                def receive_line():
                    data = b""
                    while newline not in data:
                        chunk = conn.recv(4096)
                        if not chunk:
                            raise AssertionError("bridge closed before its response")
                        data += chunk
                    line, _, remainder = data.partition(newline)
                    if remainder:
                        raise AssertionError("unexpected extra bridge packet")
                    return json.loads(line)

                hello = receive_line()
                self.assertEqual(hello["type"], "hello")
                self.assertEqual(hello["protocol"], "queue-ack-v1")
                conn.sendall(json.dumps({
                    "type": "hello_ok", "protocol": "queue-ack-v1",
                }).encode() + newline)
                message = {
                    "type": "send", "id": "gateway-message-0001",
                    "to": "owner@example.invalid", "text": "durable",
                }
                for _ in range(2):
                    conn.sendall((json.dumps(message) + chr(10)).encode())
                    self.assertEqual(receive_line(), {
                        "type": "send_ack", "id": message["id"],
                        "status": "accepted_by_bridge",
                    })
                stored = json.loads(queue_path.read_text(encoding="utf-8"))
                self.assertEqual(len(stored["outbound"]), 1)
                self.assertEqual(stored["outbound"][0]["id"], message["id"])
                self.assertEqual(stored["outbound"][0]["text"], "durable")
            finally:
                if conn is not None:
                    conn.close()
                server.close()
                proc.terminate()
                try:
                    proc.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()

    def test_inbound_text_is_replayed_after_bridge_restart(self):
        # Break: an owner message accepted while the gateway socket is down
        # disappears when the supervisor restarts the bridge.
        remember = r"""
const EventEmitter = require('events');
const Module = require('module');
const original = Module._load;
class FakeClient extends EventEmitter {
  constructor(){ super(); this.active = true; }
  execute() {
    setTimeout(() => this.emit('msg', {
      type: 'message', user: 'owner@example.invalid', body: 'remember-me',
    }), 30);
  }
  sendMessage() {}
}
Module._load = function(request, ...args) {
  if (request === './msnclient/main.js') return {MSNClient: FakeClient};
  return original.call(this, request, ...args);
};
require(process.argv[1]);
setTimeout(() => process.exit(0), 250);
"""
        replay = r"""
const EventEmitter = require('events');
const Module = require('module');
const original = Module._load;
class FakeClient extends EventEmitter {
  constructor(){ super(); this.active = true; }
  execute() {}
  sendMessage() {}
}
Module._load = function(request, ...args) {
  if (request === './msnclient/main.js') return {MSNClient: FakeClient};
  return original.call(this, request, ...args);
};
require(process.argv[1]);
"""
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = pathlib.Path(tmp) / "bridge-queue.json"
            env = bridge_env(queue_path, free_port(), free_port())
            first = subprocess.run(
                ["node", "-e", remember, str(BRIDGE)],
                env=env, capture_output=True, text=True, timeout=4,
            )
            self.assertEqual(first.returncode, 0, first.stdout[-400:] + first.stderr[-400:])
            self.assertTrue(queue_path.exists(), "inbound text was not persisted")
            stored = json.loads(queue_path.read_text(encoding="utf-8"))
            self.assertEqual(len(stored["inbound"]), 1)
            self.assertEqual(stored["inbound"][0]["sender"], "owner@example.invalid")
            self.assertEqual(stored["inbound"][0]["body"], "remember-me")
            self.assertNotIn("z" * 32, queue_path.read_text(encoding="utf-8"))

            server = socket.socket()
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            server.settimeout(2)
            port = server.getsockname()[1]
            proc = subprocess.Popen(
                ["node", "-e", replay, str(BRIDGE)],
                env=bridge_env(queue_path, port, free_port()),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    self.fail("bridge did not reconnect to the gateway")
                conn.settimeout(2)
                buf = b""
                while b"\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                hello, _, rest = buf.partition(b"\n")
                hello_packet = json.loads(hello)
                self.assertEqual(hello_packet["type"], "hello")
                self.assertEqual(hello_packet["protocol"], "queue-ack-v1")
                conn.sendall(json.dumps({
                    "type": "hello_ok", "protocol": "queue-ack-v1",
                }).encode() + bytes([10]))
                buf = rest
                try:
                    while b"\n" not in buf:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        buf += chunk
                except socket.timeout:
                    self.fail("bridge did not push the stored inbound text after hello")
                if b"\n" not in buf:
                    self.fail("bridge did not push the stored inbound text after hello")
                incoming = json.loads(buf.split(b"\n", 1)[0])
                self.assertEqual(incoming["type"], "incoming")
                self.assertEqual(incoming["sender"], "owner@example.invalid")
                self.assertEqual(incoming["body"], "remember-me")
                self.assertTrue(incoming["id"])
                stored = json.loads(queue_path.read_text(encoding="utf-8"))
                self.assertEqual(len(stored["inbound"]), 1)
                conn.sendall(json.dumps({
                    "type": "incoming_ack", "id": incoming["id"],
                }).encode() + bytes([10]))
                for _ in range(50):
                    stored = json.loads(queue_path.read_text(encoding="utf-8"))
                    if not stored["inbound"]:
                        break
                    time.sleep(0.01)
                self.assertEqual(stored["inbound"], [])
                conn.close()
            finally:
                proc.kill()
                try:
                    proc.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                server.close()


if __name__ == "__main__":
    unittest.main()
