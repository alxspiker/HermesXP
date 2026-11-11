'use strict';
// Hermes MSN bot adapter. Runs on the MODERN Hermes computer; never on Windows XP.
// Requires the experimental tutmonde/msnclient library in ./msnclient (GPLv3).
// Local-server mode: ./msnclient reads MSN_SERVER_HOST / MSN_LOGIN_URL from
// the environment (defaults are Escargot). The installer sets them to the
// local server (127.0.0.1 / http://127.0.0.1:8081/login).
const net = require('net');
const http = require('http');
const crypto = require('crypto');
const path = require('path');
const readline = require('readline');
const fs = require('fs');
const os = require('os');
const MSNClient = require('./msnclient/main.js').MSNClient;
const {NativeCall} = require('./native_call.js');
const {interfaceForXP} = require('./lan_address.js');
const offlineQueue = require('./offline_queue.js');
const {TransferStore} = require('./file_transfer.js');

const email = process.env.MSN_BOT_EMAIL;
const password = process.env.MSN_BOT_PASSWORD;
const token = process.env.HERMES_MSN_BRIDGE_TOKEN;
const owner = String(process.env.HERMES_MSN_OWNER_EMAIL || '').trim().toLowerCase();
if (!email || !password || !token || token.length < 32) {
  console.error('Set MSN_BOT_EMAIL, MSN_BOT_PASSWORD and HERMES_MSN_BRIDGE_TOKEN (32+ chars).');
  process.exit(2);
}

function bridgeQueuePath() {
  if (process.env.HERMES_MSN_BRIDGE_QUEUE) return process.env.HERMES_MSN_BRIDGE_QUEUE;
  const home = process.env.HERMES_HOME || path.join(os.homedir(), '.hermes');
  return path.join(home, 'hermesxp-bridge-queue.json');
}
const queuePath = bridgeQueuePath();
let queueState = null;
let queueBroken = false;
try {
  queueState = offlineQueue.load(queuePath);
} catch (err) {
  queueBroken = true;
  console.error('MSN offline queue unreadable; refusing to replace it:', err.message);
}
function persistQueue() {
  if (!queueState || queueBroken) return false;
  try {
    offlineQueue.save(queuePath, queueState);
    return true;
  } catch (err) {
    queueBroken = true;
    console.error('MSN offline queue write failed:', err.message);
    return false;
  }
}
let flushingOutbound = false;
function queueOutbound(text, id) {
  if (!queueState || queueBroken || !owner) return {ok: false, error: 'offline queue unreadable'};
  const packet = {to: owner, text};
  if (id !== undefined) packet.id = id;
  const result = offlineQueue.enqueueOutbound(queueState, packet);
  if (!result.ok) return result;
  if (!persistQueue()) return {ok: false, error: 'offline queue unreadable'};
  return result;
}
async function flushOutbound() {
  if (flushingOutbound || !queueState || queueBroken || client.active !== true) return;
  flushingOutbound = true;
  try {
    while (queueState.outbound.length && client.active === true) {
      const item = queueState.outbound[0];
      try {
        await client.sendMessage(item.to, item.text);
      } catch (err) {
        console.error('MSN offline flush stopped:', err.message);
        return;
      }
      if (queueState.outbound[0] && queueState.outbound[0].id === item.id) {
        offlineQueue.ack(queueState, 'outbound', item.id);
        if (!persistQueue()) return;
      }
    }
  } finally {
    flushingOutbound = false;
  }
}
function acceptOutbound(text, id) {
  const body = String(text).slice(0, 4000);
  if (id !== undefined) {
    if (typeof id !== 'string' || id.length < 1 || id.length > 128) {
      return {ok: false, error: 'invalid message id'};
    }
    const queued = queueOutbound(body, id);
    if (queued.ok && client.active === true) void flushOutbound();
    return queued;
  }
  const mustQueue = client.active !== true || flushingOutbound ||
    Boolean(queueState && queueState.outbound.length);
  if (mustQueue) {
    const queued = queueOutbound(body);
    if (queued.ok && client.active === true) void flushOutbound();
    return queued;
  }
  try {
    const pending = client.sendMessage(owner, body);
    if (pending && typeof pending.catch === 'function') {
      pending.catch(err => {
        console.error('MSN send failed; queueing:', err.message);
        const queued = queueOutbound(body);
        if (queued.ok) void flushOutbound();
      });
    }
    return {ok: true, direct: true};
  } catch (err) {
    const queued = queueOutbound(body);
    if (queued.ok && client.active === true) void flushOutbound();
    return queued.ok ? queued : {ok: false, error: err.message};
  }
}

// Standalone Hermes send_message (CLI/cron/tool subprocess) runs outside the
// gateway's Python process. Give it a narrow authenticated loopback-only way
// to ask the EXISTING logged-in MSN bot to send a text message.
const STANDALONE_SEND_PORT = Number(process.env.HERMES_MSN_STANDALONE_PORT || 18769);
const GATEWAY_PORT = Number(process.env.HERMES_MSN_GATEWAY_PORT || 18764);
if (!Number.isInteger(STANDALONE_SEND_PORT) || STANDALONE_SEND_PORT < 1 ||
    STANDALONE_SEND_PORT > 65535 ||
    !Number.isInteger(GATEWAY_PORT) || GATEWAY_PORT < 1 || GATEWAY_PORT > 65535) {
  throw new Error('Invalid MSN bridge port');
}
const MAX_SEND_BODY = 8192;
function authenticated(request) {
  const provided = request.headers['x-hermes-token'];
  if (typeof provided !== 'string') return false;
  const supplied = Buffer.from(provided, 'utf8');
  const expected = Buffer.from(token, 'utf8');
  return supplied.length === expected.length && crypto.timingSafeEqual(supplied, expected);
}
const standaloneServer = http.createServer((req, res) => {
  function reply(code, payload) {
    const body = JSON.stringify(payload);
    res.writeHead(code, {'Content-Type': 'application/json', 'Cache-Control': 'no-store'});
    res.end(body);
  }
  if (!authenticated(req)) return reply(401, {error: 'unauthorized'});
  // Native calls are controlled through the same *loopback-only* authenticated
  // interface as Hermes's MSN send_message integration. This lets a Hermes
  // tool initiate/end a call without fabricating an incoming MSN chat command.
  if (req.method === 'POST' && ['/call/start','/call/end','/call/status'].includes(req.url)) {
    if (req.headers['transfer-encoding'] ||
        (req.headers['content-length'] !== undefined &&
         req.headers['content-length'] !== '0'))
      return reply(400, {error: 'call action takes no body'});
    if (client.active !== true || !nativeCall)
      return reply(503, {error: 'native MSN calling is not connected'});
    if (req.url === '/call/status')
      return reply(200, {success: true, active: Boolean(nativeCall.call),
                         outgoing: Boolean(nativeCall.call?.initiated)});
    try {
      const ok = req.url === '/call/start' ? nativeCall.invite() : nativeCall.hangup();
      return reply(ok ? 202 : 409, {success: ok, active: Boolean(nativeCall.call),
                                   error: ok ? undefined :
                                     (req.url === '/call/start' ? 'call already active' : 'no active call')});
    } catch (error) {
      console.warn('Native call action failed:', error.message);
      return reply(503, {error: 'native MSN call signaling unavailable'});
    }
  }
  if (req.method === 'POST' && req.url === '/file/send') {
    const length = Number(req.headers['content-length']);
    if (!Number.isInteger(length) || length < 2 || length > 1024 ||
        req.headers['transfer-encoding']) return reply(413, {error: 'invalid length'});
    let body = '';
    req.on('data', chunk => {
      body += chunk.toString('utf8');
      if (Buffer.byteLength(body, 'utf8') > 1024) req.destroy();
    });
    req.on('end', () => {
      let packet;
      try {packet = JSON.parse(body);} catch {return reply(400, {error: 'invalid JSON'});}
      if (typeof packet.to !== 'string' || !owner ||
          packet.to.trim().toLowerCase() !== owner) return reply(403, {error: 'recipient not authorized'});
      if (typeof packet.name !== 'string') return reply(400, {error: 'invalid file'});
      const offered = transfers.offer(owner, packet.name);
      if (!offered.ok || offered.dial) return reply(400, {error: 'file rejected'});
      if (client.active !== true || typeof client.sendP2P !== 'function')
        return reply(503, {error: 'MSN bot is not signed in'});
      try {
        for (const part of offered.packets) client.sendP2P(owner, part);
      } catch (error) {
        console.error('MSN file offer failed:', error.message);
        return reply(503, {error: 'MSN file send failed'});
      }
      return reply(202, {success: true, queued: true, name: offered.name});
    });
    return;
  }
  if (req.method !== 'POST' || req.url !== '/send') return reply(404, {error: 'not found'});
  const length = Number(req.headers['content-length']);
  if (!Number.isInteger(length) || length < 2 || length > MAX_SEND_BODY ||
      req.headers['transfer-encoding']) return reply(413, {error: 'invalid length'});
  let body = '';
  req.on('data', chunk => {
    body += chunk.toString('utf8');
    if (Buffer.byteLength(body, 'utf8') > MAX_SEND_BODY) req.destroy();
  });
  req.on('end', async () => {
    let packet;
    try {packet = JSON.parse(body);} catch {return reply(400, {error: 'invalid JSON'});}
    if (typeof packet.to !== 'string' || !owner ||
        packet.to.trim().toLowerCase() !== owner) return reply(403, {error: 'recipient not authorized'});
    if (typeof packet.text !== 'string' || !packet.text.trim() ||
        packet.text.length > 4000) return reply(400, {error: 'invalid message'});
    const messageId = crypto.randomUUID();
    const accepted = acceptOutbound(packet.text, messageId);
    if (!accepted.ok) return reply(503, {error: accepted.error || 'MSN send failed'});
    return reply(202, {
      success: true,
      queued: true,
      offline: client.active !== true,
      status: 'queued',
      delivered: false,
      message_id: messageId,
    });
  });
});
standaloneServer.listen(STANDALONE_SEND_PORT, '127.0.0.1', () => {
  console.log('MSN standalone sender listening on loopback');
});
standaloneServer.on('error', error => {
  console.error('MSN standalone sender bind failed:', error.message);
  process.exit(1);
});

const client = new MSNClient(email, password);
const transferRoot = process.env.HERMES_MSN_TRANSFER_ROOT || path.join(
  process.env.HERMES_HOME || path.join(os.homedir(), '.hermes'), 'msn-transfers');
const transfers = new TransferStore({owner, root: transferRoot});
let nativeCall = null;
if (process.env.HERMES_MSN_NATIVE_CALL === '1') {
  if (!['13','18'].includes(process.env.MSN_BOT_PROTOCOL)) {
    console.error('Native MSN calling requires MSN_BOT_PROTOCOL=13 or 18');
    process.exit(2);
  }
  const registryPath = path.join(
    process.env.HERMES_HOME || path.join(os.homedir(), '.hermes'),
    'hermesxp-devices.json');
  const getDevice = () => {
    try {
      const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
      return (registry.devices || []).find(d =>
        d && net.isIP(d.host) === 4 && /^[0-9a-f]{64}$/i.test(d.token || ''));
    } catch { return null; }
  };
  const device = getDevice();
  const host = device && interfaceForXP(device.host, process.env.HERMES_MSN_NATIVE_IP);
  const packetMs = Number(process.env.HERMES_MSN_RTP_PACKET_MS || 20);
  if (!host || !device) {
    console.error('Native MSN calling needs paired XP on a reachable LAN interface');
    process.exit(2);
  }
  nativeCall = new NativeCall({
    client, owner, host, xpHost: device.host, token, packetMs,
  });
  nativeCall.start();
  client.on('native_signal', signal => nativeCall.onSignal(signal));
  // Discovery updates the encrypted-token pairing registry after a signed
  // challenge/response/ACK. The bridge checks both interfaces periodically,
  // so an XP DHCP lease change or host NIC switch never requires editing
  // static IP settings or manually restarting Node.
  setInterval(() => {
    const current = getDevice();
    if (!current) return;
    const currentHost = interfaceForXP(current.host, process.env.HERMES_MSN_NATIVE_IP);
    if (!currentHost) return;
    if (nativeCall.xpHost === current.host && nativeCall.host === currentHost) return;
    console.info('HermesXP LAN route changed; reinitializing native SIP/RTP peer');
    nativeCall.stop();
    nativeCall = new NativeCall({
      client, owner, host: currentHost, xpHost: current.host, token, packetMs,
    });
    nativeCall.start();
  }, 3000).unref();
}
let bridge, bridgeReady = false, reliableQueue = false;
let flushingInbound = false;
const pendingInboundAcks = new Map();
let backlog = [];
function write(obj) {
  if (!bridgeReady || !bridge) return false;
  bridge.write(JSON.stringify(obj) + '\n');
  return true;
}

async function flushInbound() {
  if (flushingInbound || !reliableQueue || !queueState || queueBroken || !bridgeReady) return;
  flushingInbound = true;
  try {
    while (queueState.inbound.length && reliableQueue && bridgeReady) {
      const item = queueState.inbound[0];
      let resolveAck;
      const acknowledged = new Promise(resolve => { resolveAck = resolve; });
      pendingInboundAcks.set(item.id, resolveAck);
      if (!write({type: 'incoming', id: item.id, sender: item.sender, body: item.body})) {
        pendingInboundAcks.delete(item.id);
        return;
      }
      let timer;
      const timeout = new Promise(resolve => {
        timer = setTimeout(() => resolve(false), 2000);
      });
      const wasAcknowledged = await Promise.race([acknowledged, timeout]);
      clearTimeout(timer);
      pendingInboundAcks.delete(item.id);
      if (!wasAcknowledged && !bridgeReady) return;
    }
  } finally {
    flushingInbound = false;
  }
}

function connectBridge() {
  const sock = net.connect({host: '127.0.0.1', port: GATEWAY_PORT});
  bridge = sock;
  let buffer = '';
  let validated = false;
  sock.on('connect', () => sock.write(JSON.stringify({
    type: 'hello', token, protocol: 'queue-ack-v1',
  }) + String.fromCharCode(10)));
  sock.on('data', data => {
    buffer += data.toString('utf8');
    if (buffer.length > 131072) {sock.destroy(); return;}
    let newline;
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline); buffer = buffer.slice(newline+1);
      let packet; try {packet = JSON.parse(line);} catch {continue;}
      if (!validated) {
        if (packet.type !== 'hello_ok') {sock.destroy(); return;}
        reliableQueue = packet.protocol === 'queue-ack-v1';
        validated = bridgeReady = true;
        console.log('Connected to Hermes gateway');
        if (queueState && !queueBroken) {
          if (reliableQueue) {
            void flushInbound();
          } else {
            while (queueState.inbound.length) {
              const queued = queueState.inbound[0];
              if (!write({type:'incoming', sender:queued.sender, body:queued.body})) break;
              queueState.inbound.shift();
              if (!persistQueue()) break;
            }
          }
        }
        for (const msg of backlog) write(msg);
        backlog=[];
        continue;
      }
      if (packet.type === 'incoming_ack' && reliableQueue &&
          typeof packet.id === 'string' && queueState && !queueBroken) {
        const exists = queueState.inbound.some(item => item.id === packet.id);
        if (exists) {
          offlineQueue.ack(queueState, 'inbound', packet.id);
          if (!persistQueue()) continue;
        }
        const resolveAck = pendingInboundAcks.get(packet.id);
        if (resolveAck) resolveAck(true);
        continue;
      }
      if (packet.type === 'send_file' && typeof packet.to === 'string' && typeof packet.name === 'string') {
        if (packet.to.toLowerCase() !== owner) {
          console.warn('Refused unexpected outbound recipient'); continue;
        }
        const offered = transfers.offer(owner, packet.name);
        if (!offered.ok || offered.dial) {
          console.warn('Refused file send'); continue;
        }
        try {
          for (const part of offered.packets) client.sendP2P(owner, part);
        } catch (err) { console.error('MSN file send error:', err.message); }
        continue;
      }
      if (packet.type === 'send' && typeof packet.to === 'string' && typeof packet.text === 'string') {
        if (packet.to.toLowerCase() !== String(process.env.HERMES_MSN_OWNER_EMAIL || '').toLowerCase()) {
          console.warn('Refused unexpected outbound recipient'); continue;
        }
        if (reliableQueue && (typeof packet.id !== 'string' || packet.id.length > 128)) {
          console.warn('Refused outbound packet without a bounded message id'); continue;
        }
        const accepted = acceptOutbound(packet.text, reliableQueue ? packet.id : undefined);
        if (!accepted.ok) {
          console.error('MSN send not accepted:', accepted.error);
        } else if (reliableQueue) {
          write({type: 'send_ack', id: packet.id, status: 'accepted_by_bridge'});
        }
      }
    }
  });
  sock.on('error', error => console.warn('Hermes bridge connection:', error.message));
  sock.on('close', () => {
    if (bridge === sock) {bridgeReady = false;reliableQueue = false;bridge = null;}
    for (const resolveAck of pendingInboundAcks.values()) resolveAck(false);
    pendingInboundAcks.clear();
    setTimeout(connectBridge, 3000);
  });
}

client.on('msg', msg => {
  if (msg && msg.type === 'connected') {
    console.log('MSN bot logged in');
    void flushOutbound();
  }
  if (msg && (msg.type === 'p2p' || msg.type === 'file_invite')) {
    const peer = String(msg.user || '').trim().toLowerCase();
    if (!owner || peer !== owner) return;
    if (msg.type === 'file_invite') {
      const declined = transfers.declineLegacy(owner, String(msg.body || ''));
      if (declined.notice) {
        try { client.sendMessage(owner, declined.notice); }
        catch (error) { console.error('MSN file decline failed:', error.message); }
      }
      return;
    }
    if (!Buffer.isBuffer(msg.payload)) return;
    const result = transfers.feed(owner, msg.payload);
    if (result && result.dial) return;
    try {
      for (const part of result.packets || []) client.sendP2P(owner, part);
    } catch (error) { console.error('MSN file reply failed:', error.message); }
    if (result.event) {
      const item = {
        type: result.event.type,
        sender: owner,
        name: result.event.name,
        size: result.event.size,
        sha256: result.event.sha256,
      };
      if (typeof result.event.relative === 'string') item.relative = result.event.relative;
      if (!write(item)) {
        if (backlog.length >= 16) backlog.shift();
        backlog.push(item);
      }
    }
    if (result.notice) {
      try { client.sendMessage(owner, result.notice); }
      catch (error) { console.error('MSN file notice failed:', error.message); }
    }
    return;
  }
  if (!msg || msg.type !== 'message' || typeof msg.user !== 'string' || typeof msg.body !== 'string') return;
  if (!owner || msg.user.trim().toLowerCase() !== owner) return;
  const command = msg.body.trim().toLowerCase();
  if (command === '/nativecall' || (command === '/call' && nativeCall)) {
    if (!nativeCall) {
      client.sendMessage(owner, 'Native MSN calling is disabled on Hermes.');
      return;
    }
    try {
      client.sendMessage(owner, nativeCall.invite()
        ? 'Native Messenger call invitation sent.'
        : 'Hermes is already handling a native call.');
    }catch(error) {
      console.error('Native MSN invite failed:', error.message);
      client.sendMessage(owner, 'Native MSN call negotiation failed.');
    }
    return;
  }
  if (command === '/hangup' && nativeCall) {
    client.sendMessage(owner, nativeCall.hangup()
      ? 'Native Messenger call ended.'
      : 'No native Messenger call is active.');
    return;
  }
  const body = msg.body.slice(0,4000);
  if (reliableQueue) {
    if (!queueState || queueBroken) {
      console.error('MSN inbound message not stored; offline queue unavailable');
      return;
    }
    const queued = offlineQueue.enqueueInbound(queueState, {
      sender: owner, body,
    });
    if (!queued.ok) {
      console.error('MSN inbound message not stored:', queued.error);
      return;
    }
    if (persistQueue()) void flushInbound();
    return;
  }
  const item = {type:'incoming',sender:owner,body};
  if (!write(item)) {
    if (queueState && !queueBroken) {
      const queued = offlineQueue.enqueueInbound(queueState, {
        sender: owner, body: item.body,
      });
      if (queued.ok && persistQueue()) return;
    }
    if (backlog.length >= 16) backlog.shift();
    backlog.push(item);
  }
});
client.on('close', () => {
  if (nativeCall) nativeCall.stop();
  console.error('MSN connection closed; exiting so the supervisor can reconnect.');
  process.exit(1);
});
client.on('error', err => console.error('MSN library error:', err));
connectBridge();
client.execute();
