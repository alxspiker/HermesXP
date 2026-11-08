'use strict';
// Hermes MSN bot adapter. Runs on the MODERN Hermes computer; never on Windows XP.
// Requires the experimental tutmonde/msnclient library in ./msnclient (GPLv3).
// Local-server mode: ./msnclient reads MSN_SERVER_HOST / MSN_LOGIN_URL from
// the environment (defaults are Escargot). The installer sets them to the
// local server (127.0.0.1 / http://127.0.0.1:8081/login).
const net = require('net');
const path = require('path');
const readline = require('readline');
const MSNClient = require('./msnclient/main.js').MSNClient;

const email = process.env.MSN_BOT_EMAIL;
const password = process.env.MSN_BOT_PASSWORD;
const token = process.env.HERMES_MSN_BRIDGE_TOKEN;
if (!email || !password || !token || token.length < 32) {
  console.error('Set MSN_BOT_EMAIL, MSN_BOT_PASSWORD and HERMES_MSN_BRIDGE_TOKEN (32+ chars).');
  process.exit(2);
}

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
client.on('close', () => console.error('MSN connection closed; restart bridge to reconnect.'));
client.on('error', err => console.error('MSN library error:', err));
connectBridge();
client.execute();
