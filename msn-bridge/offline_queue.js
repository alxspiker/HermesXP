'use strict';
// Host-local message queue for the MSN bridge. Never written on Windows XP.
// A corrupt file throws and is not rewritten by load().
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const MAX_ITEMS = 64;
const MAX_TEXT = 4000;
const MAX_COMPLETED_IDS = 256;

function emptyState() {
  return {outbound: [], inbound: [], completed: []};
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
  if (!data || !Array.isArray(data.outbound) || !Array.isArray(data.inbound) ||
      (data.completed !== undefined && !Array.isArray(data.completed))) {
    throw new Error('invalid offline queue');
  }
  const completed = data.completed || [];
  if (!data.outbound.every(validOutbound) || !data.inbound.every(validInbound) ||
      !completed.every(id => typeof id === 'string' && id.length > 0 && id.length <= 128)) {
    throw new Error('invalid offline queue item');
  }
  return {
    outbound: data.outbound.slice(),
    inbound: data.inbound.slice(),
    completed: completed.slice(-MAX_COMPLETED_IDS),
  };
}

function save(filePath, state) {
  fs.mkdirSync(path.dirname(filePath), {recursive: true, mode: 0o700});
  const tmp = filePath + '.tmp';
  const body = JSON.stringify({
    outbound: state.outbound || [],
    inbound: state.inbound || [],
    completed: (state.completed || []).slice(-MAX_COMPLETED_IDS),
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
      packet.text.length > MAX_TEXT || typeof packet.to !== 'string' ||
      (packet.id !== undefined && (typeof packet.id !== 'string' ||
       packet.id.length < 1 || packet.id.length > 128))) {
    return {ok: false, error: 'invalid message'};
  }
  const id = packet.id || crypto.randomUUID();
  const existing = state.outbound.find(item => item.id === id);
  if (existing || (state.completed || []).includes(id)) {
    return {ok: true, item: existing || null, duplicate: true};
  }
  if (state.outbound.length >= MAX_ITEMS) {
    return {ok: false, error: 'offline queue full'};
  }
  const item = {
    id,
    to: packet.to,
    text: packet.text,
    queued_at: Date.now(),
  };
  state.outbound.push(item);
  return {ok: true, item, duplicate: false};
}

function enqueueInbound(state, packet) {
  if (!state || !Array.isArray(state.inbound)) {
    return {ok: false, error: 'offline queue unreadable'};
  }
  if (typeof packet.body !== 'string' || packet.body.length < 1 ||
      packet.body.length > MAX_TEXT || typeof packet.sender !== 'string' ||
      (packet.id !== undefined && (typeof packet.id !== 'string' ||
       packet.id.length < 1 || packet.id.length > 128))) {
    return {ok: false, error: 'invalid message'};
  }
  const id = packet.id || crypto.randomUUID();
  const existing = state.inbound.find(item => item.id === id);
  if (existing) return {ok: true, item: existing, duplicate: true, dropped: 0};
  if (state.inbound.length >= MAX_ITEMS) {
    return {ok: false, error: 'offline queue full'};
  }
  const item = {
    id,
    sender: packet.sender,
    body: packet.body,
    queued_at: Date.now(),
  };
  state.inbound.push(item);
  return {ok: true, item, duplicate: false, dropped: 0};
}

function ack(state, lane, id) {
  if (!state || (lane !== 'outbound' && lane !== 'inbound') || !Array.isArray(state[lane])) {
    throw new Error('invalid offline queue');
  }
  const before = state[lane].length;
  state[lane] = state[lane].filter(item => item.id !== id);
  if (lane === 'outbound' && before !== state[lane].length) {
    const completed = Array.isArray(state.completed) ? state.completed : [];
    if (!completed.includes(id)) completed.push(id);
    state.completed = completed.slice(-MAX_COMPLETED_IDS);
  }
}

module.exports = {
  MAX_ITEMS,
  MAX_COMPLETED_IDS,
  load,
  save,
  enqueueOutbound,
  enqueueInbound,
  ack,
};
