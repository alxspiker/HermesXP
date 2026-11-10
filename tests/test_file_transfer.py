"""Host-side MSN file transfer. Does not contact the XP machine."""
import json
import os
import socket
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "SENTINEL_DO_NOT_LEAK_9f3a"


class FileTransferCases(unittest.TestCase):
    def test_node_codec_cases(self):
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "file_transfer_cases.js")],
            cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout[-500:] + result.stderr[-800:])
        self.assertIn("FILE_TRANSFER_CASES_PASS", result.stdout)

    def test_bridge_routes_files_without_dialing_or_leaking(self):
        with socket.socket() as http_listener, socket.socket() as gw_listener, socket.socket() as canary:
            http_listener.bind(("127.0.0.1", 0))
            gw_listener.bind(("127.0.0.1", 0))
            canary.bind(("127.0.0.1", 0))
            http_port = http_listener.getsockname()[1]
            gw_port = gw_listener.getsockname()[1]
            canary_port = canary.getsockname()[1]
        canary_hits = {"n": 0}
        # The bridge must not connect here. A listening socket records any dial.
        probe = socket.socket()
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", canary_port))
        probe.listen(1)
        probe.settimeout(0.2)

        root = Path(self.id().replace(".", "_"))
        # Use a private temp dir created by the harness via env; the bridge creates it.
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(probe.close)
        transfer = Path(tmp.name)
        token = "z" * 32
        harness = r'''
const EventEmitter = require('events');
const Module = require('module');
const http = require('http');
const fs = require('fs');
const path = require('path');
const original = Module._load;
const sent = [];
class FakeClient extends EventEmitter {
  constructor(){ super(); this.active = true; }
  execute(){
    const ft = require('./file_transfer.js');
    const store = new ft.TransferStore({owner: process.env.HERMES_MSN_OWNER_EMAIL, root: process.env.HERMES_MSN_TRANSFER_ROOT});
    const ctx = ft.buildContext('note.txt', Buffer.byteLength(process.env.SENTINEL));
    const body = [
      'EUF-GUID: ' + ft.FILE_GUID,
      'SessionID: 42',
      'AppID: 2',
      'Context: ' + ctx,
      '', '',
    ].join('\r\n');
    const slp = [
      'INVITE MSNMSGR:bot@example.invalid MSNSLP/1.0',
      'To: <msnmsgr:bot@example.invalid>',
      'From: <msnmsgr:owner@example.invalid>',
      'Via: MSNSLP/1.0/TLP ;branch={11111111-1111-1111-1111-111111111111}',
      'CSeq: 0 ',
      'Call-ID: {22222222-2222-2222-2222-222222222222}',
      'Max-Forwards: 0',
      'Content-Type: application/x-msnmsgr-sessionreqbody',
      'Content-Length: ' + Buffer.byteLength(body),
      '', body,
    ].join('\r\n');
    const payload = Buffer.from(slp);
    const header = Buffer.alloc(48);
    header.writeUInt32LE(0, 0);
    header.writeUInt32LE(9, 4);
    header.writeBigUInt64LE(BigInt(payload.length), 16);
    header.writeUInt32LE(payload.length, 24);
    const invite = Buffer.concat([header, payload]);
    this.emit('msg', {type:'p2p', user:'stranger@example.invalid', payload: invite});
    this.emit('msg', {type:'p2p', user:'owner@example.invalid', payload: invite});
    const data = Buffer.from(process.env.SENTINEL);
    const chunk = Buffer.alloc(48 + data.length);
    chunk.writeUInt32LE(42, 0);
    chunk.writeUInt32LE(11, 4);
    chunk.writeBigUInt64LE(BigInt(data.length), 16);
    chunk.writeUInt32LE(data.length, 24);
    data.copy(chunk, 48);
    this.emit('msg', {type:'p2p', user:'owner@example.invalid', payload: chunk});
    this.emit('msg', {type:'file_invite', user:'owner@example.invalid',
      body:'IP-Address: 127.0.0.1\r\nPort: ' + process.env.CANARY_PORT + '\r\n' + process.env.SENTINEL});
  }
  sendMessage(to, text){ sent.push({to, text}); }
  sendP2P(to, packet){ sent.push({to, p2p: Buffer.isBuffer(packet)}); }
}
Module._load = function(request, ...args){
  if (request === './msnclient/main.js') return {MSNClient: FakeClient};
  return original.call(this, request, ...args);
};
require(process.argv[1]);
function post(pathName, body, token){
  return new Promise((resolve, reject) => {
    const bytes = Buffer.from(JSON.stringify(body));
    const req = http.request({
      host:'127.0.0.1', port:Number(process.env.HERMES_MSN_STANDALONE_PORT),
      path:pathName, method:'POST',
      headers:{'X-Hermes-Token': token, 'Content-Length': bytes.length},
    }, response => {
      let data = '';
      response.on('data', b => data += b);
      response.on('end', () => resolve({code: response.statusCode, body: data}));
    });
    req.on('error', reject);
    req.end(bytes);
  });
}
setTimeout(async () => {
  try {
    fs.writeFileSync(path.join(process.env.HERMES_MSN_TRANSFER_ROOT, 'outbox', 'note.txt'), 'hello');
    const denied = await post('/file/send', {to:'owner@example.invalid', name:'note.txt'}, 'bad');
    const escaped = await post('/file/send', {to:'owner@example.invalid', name:'../secret.txt'}, 'z'.repeat(32));
    const stranger = await post('/file/send', {to:'stranger@example.invalid', name:'note.txt'}, 'z'.repeat(32));
    const ok = await post('/file/send', {to:'owner@example.invalid', name:'note.txt'}, 'z'.repeat(32));
    const inbox = fs.readdirSync(path.join(process.env.HERMES_MSN_TRANSFER_ROOT, 'inbox'));
    const stored = inbox.length === 1 && fs.readFileSync(path.join(process.env.HERMES_MSN_TRANSFER_ROOT, 'inbox', inbox[0])).toString() === process.env.SENTINEL;
    const leaked = JSON.stringify(sent).includes(process.env.SENTINEL);
    const queued = sent.some(item => item.p2p);
    const pass = denied.code === 401 && escaped.code === 400 && stranger.code === 403 &&
                 ok.code === 202 && stored && !leaked && queued;
    console.log(JSON.stringify({denied:denied.code, escaped:escaped.code, stranger:stranger.code, ok:ok.code, stored, leaked, queued}));
    console.log(pass ? 'BRIDGE_FILE_TRANSFER_PASS' : 'BRIDGE_FILE_TRANSFER_FAIL');
    process.exit(pass ? 0 : 8);
  } catch (err) {
    console.error(err);
    process.exit(9);
  }
}, 150);
'''
        env = dict(os.environ,
                   MSN_BOT_EMAIL="bot@example.invalid",
                   MSN_BOT_PASSWORD="test",
                   HERMES_MSN_OWNER_EMAIL="owner@example.invalid",
                   HERMES_MSN_BRIDGE_TOKEN=token,
                   HERMES_MSN_STANDALONE_PORT=str(http_port),
                   HERMES_MSN_GATEWAY_PORT=str(gw_port),
                   HERMES_MSN_TRANSFER_ROOT=str(transfer),
                   CANARY_PORT=str(canary_port),
                   SENTINEL=SENTINEL)
        (transfer / "inbox").mkdir()
        (transfer / "outbox").mkdir()
        result = subprocess.run(
            ["node", "-e", harness, str(ROOT / "msn-bridge" / "bridge.js")],
            cwd=ROOT / "msn-bridge", env=env, capture_output=True, text=True, timeout=5)
        accepted = 0
        while True:
            try:
                conn, _ = probe.accept()
            except socket.timeout:
                break
            accepted += 1
            conn.close()
        self.assertEqual(accepted, 0, "bridge dialed the invite address")
        self.assertEqual(result.returncode, 0, result.stdout[-600:] + result.stderr[-600:])
        self.assertIn("BRIDGE_FILE_TRANSFER_PASS", result.stdout)
        self.assertNotIn(SENTINEL, result.stdout)
