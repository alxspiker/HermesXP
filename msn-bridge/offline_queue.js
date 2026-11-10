'use strict';
// Host-local message queue for the MSN bridge. Never written on Windows XP.
// A corrupt file throws and is not rewritten by load().
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const MAX_ITEMS = 64;
const MAX_TEXT = 4000;

function emptyState() {
  return {outbound: [], inbound: []};
}

function validOutbound(item) {
  return Boolean(item) && typeof item.id === 'string' && item.id.length > 0 &&
    typeof item.to === 'string' && typeof item.text === 'string' &&
    item.text.length <= MAX_TEXT && typeof item.queued_at === 'number';
}

function validInbound(item) {
  return Boolean(item) && typeof item.id === 'string' && item.id.length > 0 &&
    typeof item.sender === 'string' && typeof item.body === 'string' &&
    item.body.length <= MAX_TEXT && typeof item.queued_at === 'number';
}

function load(filePath) {
  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf8');
  } catch (err) {
    if (err.code === 'ENOENT') return emptyState();
    throw err;
  }
  const data = JSON.parse(raw);
  if (!data || !Array.isArray(data.outbound) || !Array.isArray(data.inbound)) {
    throw new Error('invalid offline queue');
  }
  if (!data.outbound.every(validOutbound) || !data.inbound.every(validInbound)) {
    throw new Error('invalid offline queue item');
  }
  return {outbound: data.outbound.slice(), inbound: data.inbound.slice()};
}

function save(filePath, state) {
  fs.mkdirSync(path.dirname(filePath), {recursive: true, mode: 0o700});
  const tmp = filePath + '.tmp';
  const body = JSON.stringify({
    outbound: state.outbound || [],
    inbound: state.inbound || [],
  });
  const fd = fs.openSync(tmp, 'w', 0o600);
  try {
    fs.writeFileSync(fd, body);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(tmp, filePath);
  fs.chmodSync(filePath, 0o600);
}

function enqueueOutbound(state, packet) {
  if (!state || !Array.isArray(state.outbound)) {
    return {ok: false, error: 'offline queue unreadable'};
  }
  if (typeof packet.text !== 'string' || packet.text.length < 1 ||
      packet.text.length > MAX_TEXT || typeof packet.to !== 'string') {
    return {ok: false, error: 'invalid message'};
  }
  if (state.outbound.length >= MAX_ITEMS) {
    return {ok: false, error: 'offline queue full'};
  }
  const item = {
    id: crypto.randomUUID(),
    to: packet.to,
    text: packet.text,
    queued_at: Date.now(),
  };
  state.outbound.push(item);
  return {ok: true, item};
}

function enqueueInbound(state, packet) {
  if (!state || !Array.isArray(state.inbound)) {
    return {ok: false, error: 'offline queue unreadable'};
  }
  if (typeof packet.body !== 'string' || packet.body.length < 1 ||
      packet.body.length > MAX_TEXT || typeof packet.sender !== 'string') {
    return {ok: false, error: 'invalid message'};
  }
  let dropped = 0;
  while (state.inbound.length >= MAX_ITEMS) {
    state.inbound.shift();
    dropped += 1;
  }
  const item = {
    id: crypto.randomUUID(),
    sender: packet.sender,
    body: packet.body,
    queued_at: Date.now(),
  };
  state.inbound.push(item);
  return {ok: true, item, dropped};
}

function ack(state, lane, id) {
  if (!state || (lane !== 'outbound' && lane !== 'inbound') || !Array.isArray(state[lane])) {
    throw new Error('invalid offline queue');
  }
  state[lane] = state[lane].filter(item => item.id !== id);
}

module.exports = {
  MAX_ITEMS,
  load,
  save,
  enqueueOutbound,
  enqueueInbound,
  ack,
};
