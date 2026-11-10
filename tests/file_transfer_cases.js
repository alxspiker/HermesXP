'use strict';
// Host-side cases for Hermes-mediated MSN file transfer.
// Expected values are literals or stdlib hashes, not helpers from the module.
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const net = require('net');

const ft = require('../msn-bridge/file_transfer.js');
const SENTINEL = 'SENTINEL_DO_NOT_LEAK_9f3a';
const HELLO_SHA = '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824';

function le32(n) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(n >>> 0);
  return b;
}
function le64(n) {
  const b = Buffer.alloc(8);
  b.writeBigUInt64LE(BigInt(n));
  return b;
}
function handContext(filename, size) {
  const ctx = Buffer.alloc(64);
  ctx.writeUInt32LE(64, 0);
  ctx.writeUInt32LE(2, 4);
  ctx.writeBigUInt64LE(BigInt(size), 8);
  Buffer.from(filename + '\0', 'utf16le').copy(ctx, 20);
  return ctx.toString('base64');
}
function handP2P(fields, payload) {
  payload = payload || Buffer.alloc(0);
  return Buffer.concat([
    le32(fields.sessionId || 0),
    le32(fields.identifier || 1),
    le64(fields.offset || 0),
    le64(fields.totalSize == null ? payload.length : fields.totalSize),
    le32(fields.length == null ? payload.length : fields.length),
    le32(fields.flags || 0),
    le32(fields.ackId || 0),
    le32(fields.ackUid || 0),
    le64(fields.ackSize || 0),
    payload,
  ]);
}
function slpInvite(context) {
  const body = [
    'EUF-GUID: {5D3E02AB-6190-11D3-BBBB-00C04F795683}',
    'SessionID: 42',
    'AppID: 2',
    'Context: ' + context,
    '',
    '',
  ].join('\r\n');
  return [
    'INVITE MSNMSGR:bot@example.invalid MSNSLP/1.0',
    'To: <msnmsgr:bot@example.invalid>',
    'From: <msnmsgr:owner@example.invalid>',
    'Via: MSNSLP/1.0/TLP ;branch={11111111-1111-1111-1111-111111111111}',
    'CSeq: 0 ',
    'Call-ID: {22222222-2222-2222-2222-222222222222}',
    'Max-Forwards: 0',
    'Content-Type: application/x-msnmsgr-sessionreqbody',
    'Content-Length: ' + Buffer.byteLength(body),
    '',
    body,
  ].join('\r\n');
}
function tmpRoot() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'msn-ft-'));
}

function testPolicy() {
  assert.strictEqual(ft.sanitizeFilename('note.txt'), 'note.txt');
  assert.strictEqual(ft.sanitizeFilename('Owner Report (1).pdf'), 'Owner Report (1).pdf');
  for (const bad of ['../note.txt', '..\\note.txt', 'a/b.txt', 'a\\b.txt',
                     'run.exe', 'run.exe.txt', 'NUL.txt', 'CON', '.hidden',
                     '', ' note.txt', 'résumé.txt', 'x'.repeat(81) + '.txt']) {
    assert.strictEqual(ft.sanitizeFilename(bad), null, bad);
  }
  assert.strictEqual(ft.MAX_FILE_BYTES, 8388608);
  assert.strictEqual(ft.FILE_GUID, '{5D3E02AB-6190-11D3-BBBB-00C04F795683}');
}

function testHandContext() {
  const parsed = ft.parseContext(handContext('note.txt', 5));
  assert.deepStrictEqual(parsed, {filename: 'note.txt', size: 5});
  assert.strictEqual(ft.parseContext(handContext('../note.txt', 5)), null);
  assert.strictEqual(ft.parseContext(handContext('run.exe', 4)), null);
  assert.strictEqual(ft.parseContext('@@@'), null);
  const built = ft.parseContext(ft.buildContext('note.txt', 5));
  assert.deepStrictEqual(built, {filename: 'note.txt', size: 5});
}

function testHandP2P() {
  const payload = Buffer.from('hello');
  const raw = handP2P({sessionId: 42, identifier: 7, offset: 0, totalSize: 5, length: 5}, payload);
  const parsed = ft.parseP2P(raw);
  assert.strictEqual(parsed.sessionId, 42);
  assert.strictEqual(parsed.identifier, 7);
  assert.strictEqual(parsed.offset, 0);
  assert.strictEqual(parsed.totalSize, 5);
  assert.strictEqual(parsed.length, 5);
  assert.strictEqual(parsed.payload.toString(), 'hello');
  assert.strictEqual(ft.parseP2P(Buffer.from('short')), null);
}

function testInbound(root) {
  const store = new ft.TransferStore({
    owner: 'owner@example.invalid',
    root,
    maxBytes: ft.MAX_FILE_BYTES,
  });
  const invite = Buffer.from(slpInvite(handContext('note.txt', 5)));
  const packet = handP2P({sessionId: 0, identifier: 9, totalSize: invite.length, length: invite.length}, invite);
  const accepted = store.receive('Owner@Example.Invalid', packet);
  assert.strictEqual(accepted.dial, false);
  assert.ok(accepted.packets.length >= 1);
  const ack = ft.parseP2P(accepted.packets[0]);
  assert.strictEqual(ack.flags, 0x02);
  assert.strictEqual(ack.length, 0);
  assert.strictEqual(ack.ackId, 9);

  const stranger = store.receive('stranger@example.invalid', packet);
  assert.strictEqual(stranger.dial, false);
  assert.strictEqual(stranger.event, undefined);

  const wrongGuid = slpInvite(handContext('note.txt', 5)).replace(ft.FILE_GUID, '{00000000-0000-0000-0000-000000000000}');
  const wrong = store.receive('owner@example.invalid', handP2P({totalSize: wrongGuid.length, length: wrongGuid.length}, Buffer.from(wrongGuid)));
  assert.strictEqual(wrong.dial, false);
  assert.strictEqual(wrong.event, undefined);

  const huge = slpInvite(handContext('note.txt', 8388609));
  const tooBig = store.receive('owner@example.invalid', handP2P({totalSize: huge.length, length: huge.length}, Buffer.from(huge)));
  assert.strictEqual(tooBig.event, undefined);
  assert.strictEqual(tooBig.dial, false);

  const part = Buffer.from('hel');
  const data1 = handP2P({sessionId: 42, identifier: 11, offset: 0, totalSize: 5, length: 3}, part);
  const mid = store.receive('owner@example.invalid', data1);
  assert.strictEqual(mid.event, undefined);
  assert.strictEqual(ft.parseP2P(mid.packets[0]).flags, 0x02);

  const hole = handP2P({sessionId: 42, identifier: 12, offset: 0, totalSize: 5, length: 2}, Buffer.from('lo'));
  const rejected = store.receive('owner@example.invalid', hole);
  assert.strictEqual(rejected.event, undefined);
  assert.strictEqual(fs.readdirSync(path.join(root, 'inbox')).length, 0);

  const again = store.receive('owner@example.invalid', packet);
  assert.strictEqual(again.dial, false);
  store.receive('owner@example.invalid', data1);
  const tail = Buffer.from('lo');
  const data2 = handP2P({sessionId: 42, identifier: 13, offset: 3, totalSize: 5, length: 2}, tail);
  const done = store.receive('owner@example.invalid', data2);
  assert.strictEqual(done.dial, false);
  assert.ok(done.event);
  assert.strictEqual(done.event.type, 'incoming_file');
  assert.strictEqual(done.event.name, 'note.txt');
  assert.strictEqual(done.event.size, 5);
  assert.strictEqual(done.event.sha256, HELLO_SHA);
  assert.strictEqual(done.event.contents, undefined);
  const dumped = JSON.stringify(done.event) + String(done.notice || '');
  assert.strictEqual(dumped.includes('hello'), false);
  assert.strictEqual(dumped.includes(SENTINEL), false);
  const stored = fs.readFileSync(path.join(root, 'inbox', done.event.relative));
  assert.strictEqual(stored.toString(), 'hello');
  assert.strictEqual(fs.statSync(path.join(root, 'inbox', done.event.relative)).mode & 0o777, 0o644);
  assert.strictEqual(path.isAbsolute(done.event.relative), false);
  assert.strictEqual(done.event.relative.includes('..'), false);
}

function testSentinelNotLeaked(root) {
  const store = new ft.TransferStore({owner: 'owner@example.invalid', root});
  const body = Buffer.from(SENTINEL);
  const invite = Buffer.from(slpInvite(handContext('note.txt', body.length)));
  store.receive('owner@example.invalid', handP2P({totalSize: invite.length, length: invite.length}, invite));
  const done = store.receive('owner@example.invalid', handP2P({
    sessionId: 42, identifier: 3, offset: 0, totalSize: body.length, length: body.length,
  }, body));
  const dumped = JSON.stringify(done.event) + String(done.notice || '');
  assert.strictEqual(dumped.includes(SENTINEL), false);
  assert.strictEqual(done.event.sha256, crypto.createHash('sha256').update(body).digest('hex'));
}

function testOutbound(root) {
  const out = path.join(root, 'outbox');
  fs.mkdirSync(out, {recursive: true});
  fs.writeFileSync(path.join(out, 'note.txt'), 'hello');
  const outside = path.join(root, 'secret.txt');
  fs.writeFileSync(outside, SENTINEL);
  fs.symlinkSync(outside, path.join(out, 'link.txt'));
  const store = new ft.TransferStore({owner: 'owner@example.invalid', root});
  const escaped = store.offer('owner@example.invalid', 'link.txt');
  assert.strictEqual(escaped.ok, false);
  assert.strictEqual(escaped.dial, false);
  assert.deepStrictEqual(escaped.packets, []);
  const traversal = store.offer('owner@example.invalid', '../secret.txt');
  assert.strictEqual(traversal.ok, false);
  assert.strictEqual(traversal.dial, false);

  const offered = store.offer('owner@example.invalid', 'note.txt');
  assert.strictEqual(offered.ok, true);
  assert.strictEqual(offered.dial, false);
  assert.strictEqual(offered.name, 'note.txt');
  const invite = ft.parseP2P(offered.packets[0]);
  assert.ok(invite.payload.toString('latin1').includes('INVITE '));
  const ctx = invite.payload.toString('latin1').match(/Context: ([A-Za-z0-9+/=]+)/);
  assert.ok(ctx);
  assert.deepStrictEqual(ft.parseContext(ctx[1]), {filename: 'note.txt', size: 5});

  const okBody = 'SessionID: 1\r\n\r\n';
  const ok = [
    'MSNSLP/1.0 200 OK',
    'To: <msnmsgr:owner@example.invalid>',
    'From: <msnmsgr:bot@example.invalid>',
    'Via: MSNSLP/1.0/TLP ;branch={11111111-1111-1111-1111-111111111111}',
    'CSeq: 1 ',
    'Call-ID: ' + offered.callId,
    'Max-Forwards: 0',
    'Content-Type: application/x-msnmsgr-sessionreqbody',
    'Content-Length: ' + Buffer.byteLength(okBody),
    '',
    okBody,
  ].join('\r\n');
  const progressed = store.feed('owner@example.invalid', handP2P({
    totalSize: ok.length, length: ok.length,
  }, Buffer.from(ok)));
  assert.strictEqual(progressed.dial, false);
  const data = progressed.packets.map(ft.parseP2P).filter(p => p.length > 0);
  const bytes = Buffer.concat(data.map(p => p.payload));
  assert.strictEqual(bytes.toString(), 'hello');
  assert.strictEqual(progressed.event, undefined);
  const last = data[data.length - 1];
  const acked = store.feed('owner@example.invalid', handP2P({
    flags: 0x02, length: 0, totalSize: 0, ackId: last.identifier, ackSize: 5,
  }, Buffer.alloc(0)));
  assert.strictEqual(acked.dial, false);
  assert.strictEqual(acked.event && acked.event.type, 'outgoing_file');
  assert.strictEqual(acked.event.sha256, HELLO_SHA);
  assert.strictEqual(JSON.stringify(acked.event).includes(SENTINEL), false);
}

function testLegacyDoesNotDial() {
  const root = tmpRoot();
  const store = new ft.TransferStore({owner: 'owner@example.invalid', root});
  const invite = [
    'Invitation-Command: INVITE',
    'Application-Name: File Transfer',
    'Application-File: note.txt',
    'Application-FileSize: 5',
    'IP-Address: 127.0.0.1',
    'Port: 9',
    SENTINEL,
  ].join('\r\n');
  const declined = store.declineLegacy('owner@example.invalid', invite);
  assert.strictEqual(declined.dial, false);
  assert.deepStrictEqual(declined.packets, []);
  assert.strictEqual(String(declined.notice).includes(SENTINEL), false);
  assert.strictEqual(String(declined.notice).includes('127.0.0.1'), false);
}

async function testCanaryPortUntouched() {
  const root = tmpRoot();
  const store = new ft.TransferStore({owner: 'owner@example.invalid', root});
  const hits = [];
  const server = net.createServer(sock => { hits.push(sock.remoteAddress); sock.destroy(); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const invite = 'IP-Address: 127.0.0.1\r\nPort: ' + port + '\r\n' + SENTINEL;
  const declined = store.declineLegacy('owner@example.invalid', invite);
  assert.strictEqual(declined.dial, false);
  await new Promise(resolve => setTimeout(resolve, 50));
  server.close();
  assert.strictEqual(hits.length, 0);
}

function loadSwitchboard() {
  const Module = require('module');
  const original = Module._load;
  Module._load = function(request, parent, isMain) {
    if (request === 'axios') return {};
    return original.call(this, request, parent, isMain);
  };
  const main = require('../msn-bridge/msnclient/main.js');
  Module._load = original;
  return main.MSNSwitchBoard;
}

function mimeFrame(contentType, body, extra) {
  const head = Buffer.from(
    'MIME-Version: 1.0\r\nContent-Type: ' + contentType + '\r\n' +
    'X-MMS-IM-Format: FN=Arial\r\n' + (extra || '') + '\r\n');
  const payload = Buffer.isBuffer(body) ? body : Buffer.from(body);
  const mime = Buffer.concat([head, payload]);
  return Buffer.concat([
    Buffer.from('MSG owner@example.invalid Owner ' + mime.length + '\r\n'),
    mime,
  ]);
}

async function testSwitchboardFramesP2PAndDoesNotDial() {
  const MSNSwitchBoard = loadSwitchboard();
  assert.strictEqual(typeof MSNSwitchBoard, 'function');
  const hits = [];
  const canary = net.createServer(sock => { hits.push(1); sock.destroy(); });
  await new Promise(resolve => canary.listen(0, '127.0.0.1', resolve));
  const port = canary.address().port;
  const sb = new MSNSwitchBoard('127.0.0.1', 1, 'owner@example.invalid', 'bot@example.invalid');
  sb.switchboard.connect = () => {};
  const seen = [];
  sb.on('msg', msg => seen.push(msg));
  sb.execute();
  const payload = handP2P({sessionId: 42, identifier: 4, totalSize: 5, length: 5}, Buffer.from('hello'));
  const frame = mimeFrame('application/x-msnmsgrp2p', payload, 'P2P-Dest: bot@example.invalid\r\n');
  sb.switchboard.emit('data', frame.subarray(0, 20));
  sb.switchboard.emit('data', frame.subarray(20));
  const textBody = 'Hello from owner';
  const text = mimeFrame('text/plain; charset=UTF-8', textBody + '\r\n');
  sb.switchboard.emit('data', text);
  const invite = [
    'Invitation-Command: INVITE',
    'Application-Name: File Transfer',
    'Application-File: note.txt',
    'IP-Address: 127.0.0.1',
    'Port: ' + port,
    SENTINEL,
    '',
  ].join('\r\n');
  sb.switchboard.emit('data', mimeFrame('text/x-msmsgsinvite; charset=UTF-8', invite));
  await new Promise(resolve => setTimeout(resolve, 40));
  const p2p = seen.find(msg => msg && msg.type === 'p2p');
  assert.ok(p2p, 'split P2P MSG did not emit one p2p event');
  assert.strictEqual(p2p.user, 'owner@example.invalid');
  assert.ok(p2p.payload.equals(payload));
  const textEvent = seen.find(msg => msg && msg.type === 'message');
  assert.strictEqual(textEvent && textEvent.body, textBody);
  const legacy = seen.find(msg => msg && msg.type === 'file_invite');
  assert.ok(legacy, 'direct file invite was not separated from chat text');
  assert.strictEqual(seen.some(msg => msg && msg.type === 'message' && String(msg.body).includes(SENTINEL)), false);
  const written = [];
  sb.switchboard.write = chunk => written.push(Buffer.from(chunk));
  sb.sendP2P('owner@example.invalid', payload);
  const raw = Buffer.concat(written).toString('latin1');
  assert.ok(/^MSG \d+ D \d+\r\n/.test(raw), raw.slice(0, 40));
  assert.ok(raw.includes('application/x-msnmsgrp2p'));
  assert.strictEqual(hits.length, 0);
  sb.switchboard.destroy();
  canary.close();
}

(async () => {
  testPolicy();
  testHandContext();
  testHandP2P();
  const root = tmpRoot();
  fs.mkdirSync(path.join(root, 'inbox'), {recursive: true});
  testInbound(root);
  testSentinelNotLeaked(tmpRoot());
  testOutbound(tmpRoot());
  testLegacyDoesNotDial();
  await testCanaryPortUntouched();
  await testSwitchboardFramesP2PAndDoesNotDial();
  console.log('FILE_TRANSFER_CASES_PASS');
})().catch(err => {
  console.error(err);
  process.exit(1);
});
