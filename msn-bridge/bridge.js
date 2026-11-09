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

const email = process.env.MSN_BOT_EMAIL;
const password = process.env.MSN_BOT_PASSWORD;
const token = process.env.HERMES_MSN_BRIDGE_TOKEN;
const owner = String(process.env.HERMES_MSN_OWNER_EMAIL || '').trim().toLowerCase();
if (!email || !password || !token || token.length < 32) {
  console.error('Set MSN_BOT_EMAIL, MSN_BOT_PASSWORD and HERMES_MSN_BRIDGE_TOKEN (32+ chars).');
  process.exit(2);
}

// Standalone Hermes send_message (CLI/cron/tool subprocess) runs outside the
// gateway's Python process. Give it a narrow authenticated loopback-only way
// to ask the EXISTING logged-in MSN bot to send a text message.
const STANDALONE_SEND_PORT = Number(process.env.HERMES_MSN_STANDALONE_PORT || 18769);
if (!Number.isInteger(STANDALONE_SEND_PORT) || STANDALONE_SEND_PORT < 1 ||
    STANDALONE_SEND_PORT > 65535) {
  throw new Error('Invalid standalone MSN bridge port');
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
    if (client.active !== true) return reply(503, {error: 'MSN bot is not signed in'});
    try {
      await client.sendMessage(owner, packet.text);
      return reply(202, {success: true, queued: true});
    } catch (error) {
      console.error('MSN standalone send failed:', error.message);
      return reply(503, {error: 'MSN send failed'});
    }
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
let bridge, bridgeReady = false;
let backlog = [];
function write(obj) {
  if (!bridgeReady || !bridge) return false;
  bridge.write(JSON.stringify(obj) + '\n');
  return true;
}

function connectBridge() {
  const sock = net.connect({host: '127.0.0.1', port: 18764});
  bridge = sock;
  let buffer = '';
  let validated = false;
  sock.on('connect', () => sock.write(JSON.stringify({type: 'hello', token}) + '\n'));
  sock.on('data', data => {
    buffer += data.toString('utf8');
    if (buffer.length > 131072) {sock.destroy(); return;}
    let newline;
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline); buffer = buffer.slice(newline+1);
      let packet; try {packet = JSON.parse(line);} catch {continue;}
      if (!validated) {
        if (packet.type !== 'hello_ok') {sock.destroy(); return;}
        validated = bridgeReady = true;
        console.log('Connected to Hermes gateway');
        for (const msg of backlog) write(msg);
        backlog=[];
        continue;
      }
      if (packet.type === 'send' && typeof packet.to === 'string' && typeof packet.text === 'string') {
        if (packet.to.toLowerCase() !== String(process.env.HERMES_MSN_OWNER_EMAIL || '').toLowerCase()) {
          console.warn('Refused unexpected outbound recipient'); continue;
        }
        try { client.sendMessage(packet.to, packet.text); }
        catch (err) { console.error('MSN send error:', err.message); }
      }
    }
  });
  sock.on('error', error => console.warn('Hermes bridge connection:', error.message));
  sock.on('close', () => {
    if (bridge === sock) {bridgeReady = false;bridge = null;}
    setTimeout(connectBridge, 3000);
  });
}

client.on('msg', msg => {
  if (msg && msg.type === 'connected') console.log('MSN bot logged in');
  if (!msg || msg.type !== 'message' || typeof msg.user !== 'string' || typeof msg.body !== 'string') return;
  const owner = String(process.env.HERMES_MSN_OWNER_EMAIL || '').trim().toLowerCase();
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
  const item = {type:'incoming',sender:owner,body:msg.body.slice(0,4000)};
  if (!write(item)) {
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
