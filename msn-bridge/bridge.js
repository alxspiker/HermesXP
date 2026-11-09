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
const MSNClient = require('./msnclient/main.js').MSNClient;

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
const STANDALONE_SEND_PORT = 18769;
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
  const item = {type:'incoming',sender:owner,body:msg.body.slice(0,4000)};
  if (!write(item)) {
    if (backlog.length >= 16) backlog.shift();
    backlog.push(item);
  }
});
client.on('close', () => {
  console.error('MSN connection closed; exiting so the supervisor can reconnect.');
  process.exit(1);
});
client.on('error', err => console.error('MSN library error:', err));
connectBridge();
client.execute();
