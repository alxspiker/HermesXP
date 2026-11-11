'use strict';
// In-band MSN file transfer mediated by Hermes.
// Never dials an address from an invite. Never returns file bytes to chat.
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const FILE_GUID = '{5D3E02AB-6190-11D3-BBBB-00C04F795683}';
const MAX_FILE_BYTES = 8388608;
const MAX_ACTIVE_TRANSFERS = 4;
const ACK_FLAG = 0x02;
const CHUNK = 1200;
const CONTEXT_BYTES = 574;
const BLOCKED = /(?:^|\.)(exe|bat|cmd|com|scr|pif|vbs|vbe|js|jse|wsf|wsh|msi|dll|lnk|ps1|hta|cpl|msc|jar|gadget)(?:\.|$)/i;
const RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,79}$/;

function sanitizeFilename(name) {
  if (typeof name !== 'string' || name.length < 1 || name.length > 80) return null;
  if (!NAME_RE.test(name)) return null;
  if (RESERVED.test(name.split('.')[0])) return null;
  if (BLOCKED.test(name)) return null;
  return name;
}

function parseContext(b64, maxBytes = MAX_FILE_BYTES) {
  if (typeof b64 !== 'string' || !b64) return null;
  const raw = Buffer.from(b64, 'base64');
  if (raw.length < 22) return null;
  const declared = raw.readUInt32LE(0);
  if (declared < 22 || declared > 4096) return null;
  const version = raw.readUInt32LE(4);
  if (version !== 2 && version !== 3) return null;
  const size = Number(raw.readBigUInt64LE(8));
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > MAX_FILE_BYTES) return null;
  if (!Number.isSafeInteger(size) || size < 1 || size > maxBytes) return null;
  let filename = '';
  for (let i = 20; i + 1 < raw.length && filename.length < 81; i += 2) {
    const code = raw.readUInt16LE(i);
    if (code === 0) break;
    filename += String.fromCharCode(code);
  }
  filename = sanitizeFilename(filename);
  if (!filename) return null;
  return {filename, size};
}

function buildContext(filename, size) {
  const safe = sanitizeFilename(filename);
  if (!safe || !Number.isSafeInteger(size) || size < 1 || size > MAX_FILE_BYTES) {
    throw new Error('invalid file context');
  }
  const ctx = Buffer.alloc(CONTEXT_BYTES);
  ctx.writeUInt32LE(CONTEXT_BYTES, 0);
  ctx.writeUInt32LE(2, 4);
  ctx.writeBigUInt64LE(BigInt(size), 8);
  Buffer.from(safe + '\0', 'utf16le').copy(ctx, 20);
  return ctx.toString('base64');
}

function parseP2P(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 48) return null;
  const length = buffer.readUInt32LE(24);
  if (length > MAX_FILE_BYTES || buffer.length < 48 + length) return null;
  const offset = Number(buffer.readBigUInt64LE(8));
  const totalSize = Number(buffer.readBigUInt64LE(16));
  if (!Number.isSafeInteger(offset) || !Number.isSafeInteger(totalSize)) return null;
  return {
    sessionId: buffer.readUInt32LE(0),
    identifier: buffer.readUInt32LE(4),
    offset,
    totalSize,
    length,
    flags: buffer.readUInt32LE(28),
    ackId: buffer.readUInt32LE(32),
    ackUid: buffer.readUInt32LE(36),
    ackSize: Number(buffer.readBigUInt64LE(40)),
    payload: Buffer.from(buffer.subarray(48, 48 + length)),
  };
}

function ident() {
  return crypto.randomBytes(4).readUInt32LE(0) || 1;
}

function buildP2P(fields) {
  const payload = Buffer.isBuffer(fields.payload) ? fields.payload : Buffer.alloc(0);
  const header = Buffer.alloc(48);
  header.writeUInt32LE((fields.sessionId || 0) >>> 0, 0);
  header.writeUInt32LE((fields.identifier || ident()) >>> 0, 4);
  header.writeBigUInt64LE(BigInt(fields.offset || 0), 8);
  header.writeBigUInt64LE(BigInt(fields.totalSize || 0), 16);
  const length = fields.length == null ? payload.length : fields.length;
  header.writeUInt32LE(length >>> 0, 24);
  header.writeUInt32LE((fields.flags || 0) >>> 0, 28);
  header.writeUInt32LE((fields.ackId || 0) >>> 0, 32);
  header.writeUInt32LE((fields.ackUid || 0) >>> 0, 36);
  header.writeBigUInt64LE(BigInt(fields.ackSize || 0), 40);
  return Buffer.concat([header, payload, Buffer.alloc(4)]);
}

function p2pPayload(mimeBody) {
  if (!Buffer.isBuffer(mimeBody)) return null;
  const split = mimeBody.indexOf('\r\n\r\n');
  if (split < 0) return null;
  const headers = mimeBody.subarray(0, split).toString('latin1');
  if (!/content-type:\s*application\/x-msnmsgrp2p/i.test(headers)) return null;
  return Buffer.from(mimeBody.subarray(split + 4));
}

function ackFor(header) {
  return buildP2P({
    sessionId: header.sessionId,
    identifier: ident(),
    offset: 0,
    totalSize: header.totalSize,
    length: 0,
    flags: ACK_FLAG,
    ackId: header.identifier,
    ackUid: header.ackId,
    ackSize: header.totalSize,
    payload: Buffer.alloc(0),
  });
}

function parseSLP(payload) {
  const text = payload.toString('latin1');
  const parts = text.split('\r\n\r\n');
  const lines = (parts[0] || '').split('\r\n');
  const headers = {};
  for (const line of lines.slice(1)) {
    const i = line.indexOf(':');
    if (i > 0) headers[line.slice(0, i).toLowerCase()] = line.slice(i + 1).trim();
  }
  const bodyHeaders = {};
  for (const line of (parts[1] || '').split('\r\n')) {
    const i = line.indexOf(':');
    if (i > 0) bodyHeaders[line.slice(0, i).toLowerCase()] = line.slice(i + 1).trim();
  }
  return {start: lines[0] || '', headers, bodyHeaders};
}

function slpPacket(text) {
  const payload = Buffer.from(text, 'latin1');
  return buildP2P({
    sessionId: 0,
    identifier: ident(),
    offset: 0,
    totalSize: payload.length,
    length: payload.length,
    payload,
  });
}

class TransferStore {
  constructor({owner, root, maxBytes}) {
    this.owner = String(owner || '').trim().toLowerCase();
    this.root = path.resolve(root);
    this.inbox = path.join(this.root, 'inbox');
    this.outbox = path.join(this.root, 'outbox');
    this.maxBytes = Number.isSafeInteger(maxBytes) && maxBytes >= 1
      ? Math.min(maxBytes, MAX_FILE_BYTES)
      : MAX_FILE_BYTES;
    this.inbound = new Map();
    this.outbound = new Map();
  }

  _owned(peer) {
    return this.owner.length > 0 && String(peer || '').trim().toLowerCase() === this.owner;
  }

  _ensure(dir) {
    fs.mkdirSync(dir, {recursive: true, mode: 0o700});
  }

  receive(peer, buffer) {
    return this.feed(peer, buffer);
  }

  feed(peer, buffer) {
    if (!this._owned(peer)) return {packets: [], dial: false};
    const header = parseP2P(buffer);
    if (!header) return {packets: [], dial: false, reason: 'malformed'};
    if (header.length > 0 && this.inbound.has(header.sessionId)) return this._onData(header);
    const text = header.payload.toString('latin1');
    if (header.length > 0 && /^(INVITE |MSNSLP\/1\.0 )/i.test(text)) {
      return this._onSLP(header, text);
    }
    if ((header.flags & ACK_FLAG) !== 0 && header.length === 0) return this._onAck(header);
    return this._onData(header);
  }

  _decline(slp) {
    const body = 'SessionID: ' + (slp.bodyHeaders.sessionid || '0') + '\r\n\r\n';
    const text = [
      'MSNSLP/1.0 603 Decline',
      'To: ' + (slp.headers.from || ''),
      'From: ' + (slp.headers.to || ''),
      'Via: ' + (slp.headers.via || ''),
      'CSeq: 1 ',
      'Call-ID: ' + (slp.headers['call-id'] || ''),
      'Max-Forwards: 0',
      'Content-Type: application/x-msnmsgr-sessionreqbody',
      'Content-Length: ' + Buffer.byteLength(body),
      '',
      body,
    ].join('\r\n');
    return slpPacket(text);
  }

  _ok(slp, sessionId) {
    const body = 'SessionID: ' + sessionId + '\r\n\r\n';
    const text = [
      'MSNSLP/1.0 200 OK',
      'To: ' + (slp.headers.from || ''),
      'From: ' + (slp.headers.to || ''),
      'Via: ' + (slp.headers.via || ''),
      'CSeq: 1 ',
      'Call-ID: ' + (slp.headers['call-id'] || ''),
      'Max-Forwards: 0',
      'Content-Type: application/x-msnmsgr-sessionreqbody',
      'Content-Length: ' + Buffer.byteLength(body),
      '',
      body,
    ].join('\r\n');
    return slpPacket(text);
  }

  _onSLP(header, text) {
    const slp = parseSLP(header.payload);
    if (/^INVITE /i.test(slp.start)) {
      const guid = (slp.bodyHeaders['euf-guid'] || '').toUpperCase();
      const addressed = /ip-address|ipv4internal|\bport:|listening:|bridge:/i.test(text);
      if (guid !== FILE_GUID || addressed) {
        return {packets: [this._decline(slp)], dial: false, reason: 'refused'};
      }
      const ctx = parseContext(slp.bodyHeaders.context || '', this.maxBytes);
      const sessionId = Number(slp.bodyHeaders.sessionid);
      if (!ctx || !Number.isInteger(sessionId) || sessionId <= 0) {
        return {packets: [this._decline(slp)], dial: false, reason: 'rejected file'};
      }
      if (this.inbound.has(sessionId) || this.inbound.size >= MAX_ACTIVE_TRANSFERS) {
        return {packets: [this._decline(slp)], dial: false, reason: 'transfer limit'};
      }
      this.inbound.set(sessionId, {
        size: ctx.size,
        name: ctx.filename,
        got: 0,
        chunks: [],
      });
      return {packets: [ackFor(header), this._ok(slp, sessionId)], dial: false};
    }
    if (/^MSNSLP\/1\.0 200/i.test(slp.start)) {
      const pending = this.outbound.get(slp.headers['call-id']);
      if (!pending || pending.phase !== 'invited') return {packets: [], dial: false};
      const packets = [];
      const ids = [];
      for (let offset = 0; offset < pending.bytes.length; offset += CHUNK) {
        const payload = pending.bytes.subarray(offset, Math.min(offset + CHUNK, pending.bytes.length));
        const identifier = ident();
        ids.push(identifier);
        packets.push(buildP2P({
          sessionId: pending.sessionId,
          identifier,
          offset,
          totalSize: pending.bytes.length,
          length: payload.length,
          payload,
        }));
      }
      pending.phase = 'sent';
      pending.dataIds = ids;
      return {packets, dial: false};
    }
    if (/^MSNSLP\/1\.0 (603|500|BYE)\b/i.test(slp.start)) {
      const isBye = /^MSNSLP\/1\.0 BYE\b/i.test(slp.start);
      const sessionId = Number(slp.bodyHeaders.sessionid);
      const inboundRemoved = Number.isInteger(sessionId) && this.inbound.delete(sessionId);
      const outboundRemoved = this.outbound.delete(slp.headers['call-id']);
      return {
        packets: isBye && inboundRemoved ? [this._ok(slp, sessionId)] : [],
        dial: false,
        reason: inboundRemoved || outboundRemoved ? 'cancelled' : 'no pending transfer',
      };
    }
    return {packets: [], dial: false};
  }

  _onData(header) {
    const session = this.inbound.get(header.sessionId);
    if (!session) return {packets: [], dial: false, reason: 'no session'};
    const end = header.offset + header.length;
    if (header.totalSize !== session.size || header.offset !== session.got || end > session.size || header.payload.length !== header.length) {
      this.inbound.delete(header.sessionId);
      return {packets: [], dial: false, reason: 'corrupt chunk'};
    }
    session.chunks.push(header.payload);
    session.got = end;
    const packets = [ackFor(header)];
    if (session.got !== session.size) return {packets, dial: false};
    const bytes = Buffer.concat(session.chunks, session.size);
    this.inbound.delete(header.sessionId);
    if (bytes.length !== session.size) return {packets: [], dial: false, reason: 'size mismatch'};
    const event = this._writeInbox(session.name, bytes);
    return {
      packets,
      dial: false,
      event,
      notice: 'Received ' + session.name + ' (' + session.size + ' bytes).',
    };
  }

  _writeInbox(name, bytes) {
    this._ensure(this.inbox);
    const relative = crypto.randomBytes(8).toString('hex') + '_' + name;
    const dest = path.join(this.inbox, relative);
    const fd = fs.openSync(dest, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY, 0o644);
    try {
      fs.writeSync(fd, bytes);
      fs.fchmodSync(fd, 0o644);
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    const inboxReal = fs.realpathSync(this.inbox);
    const real = fs.realpathSync(dest);
    if (real !== path.join(inboxReal, relative)) {
      fs.unlinkSync(dest);
      throw new Error('inbox escape');
    }
    return {
      type: 'incoming_file',
      sender: this.owner,
      name,
      size: bytes.length,
      sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
      relative,
    };
  }

  _onAck(header) {
    for (const pending of this.outbound.values()) {
      if (pending.phase !== 'sent' || !pending.dataIds.length) continue;
      if (header.ackId !== pending.dataIds[pending.dataIds.length - 1]) continue;
      pending.phase = 'done';
      return {
        packets: [],
        dial: false,
        event: {
          type: 'outgoing_file',
          name: pending.name,
          size: pending.bytes.length,
          sha256: crypto.createHash('sha256').update(pending.bytes).digest('hex'),
          to: this.owner,
        },
        notice: 'Offered ' + pending.name + ' (' + pending.bytes.length + ' bytes).',
      };
    }
    return {packets: [], dial: false};
  }

  offer(peer, basename) {
    const fail = reason => ({ok: false, packets: [], dial: false, reason});
    if (!this._owned(peer)) return fail('recipient not authorized');
    if (this.outbound.size >= MAX_ACTIVE_TRANSFERS) return fail('transfer limit');
    const name = sanitizeFilename(basename);
    if (!name || basename !== name) return fail('basename rejected');
    this._ensure(this.outbox);
    const candidate = path.join(this.outbox, name);
    let listed;
    try { listed = fs.lstatSync(candidate); }
    catch { return fail('not in outbox'); }
    if (!listed.isFile() && !listed.isSymbolicLink()) return fail('not a file');
    let real;
    try { real = fs.realpathSync(candidate); }
    catch { return fail('not in outbox'); }
    const outReal = fs.realpathSync(this.outbox);
    const inside = real.startsWith(outReal + path.sep);
    if (!inside) return fail('outbox escape');
    const st = fs.statSync(real);
    if (!st.isFile() || st.size < 1 || st.size > this.maxBytes) return fail('rejected file');
    const bytes = fs.readFileSync(real);
    if (bytes.length !== st.size) return fail('size changed');
    const callId = '{' + crypto.randomUUID().toUpperCase() + '}';
    const sessionId = ident();
    const body = [
      'EUF-GUID: ' + FILE_GUID,
      'SessionID: ' + sessionId,
      'AppID: 2',
      'Context: ' + buildContext(name, bytes.length),
      '',
      '',
    ].join('\r\n');
    const slp = [
      'INVITE MSNMSGR:' + this.owner + ' MSNSLP/1.0',
      'To: <msnmsgr:' + this.owner + '>',
      'From: <msnmsgr:hermes@hermes.local>',
      'Via: MSNSLP/1.0/TLP ;branch={' + crypto.randomUUID().toUpperCase() + '}',
      'CSeq: 0 ',
      'Call-ID: ' + callId,
      'Max-Forwards: 0',
      'Content-Type: application/x-msnmsgr-sessionreqbody',
      'Content-Length: ' + Buffer.byteLength(body),
      '',
      body,
    ].join('\r\n');
    this.outbound.set(callId, {name, bytes, sessionId, phase: 'invited', dataIds: []});
    return {ok: true, packets: [slpPacket(slp)], dial: false, callId, name};
  }

  declineLegacy(_peer, _inviteText) {
    return {
      dial: false,
      packets: [],
      notice: 'File transfer declined. Direct connections are not accepted.',
    };
  }
}

module.exports = {
  FILE_GUID,
  MAX_FILE_BYTES,
  sanitizeFilename,
  parseContext,
  buildContext,
  parseP2P,
  buildP2P,
  p2pPayload,
  TransferStore,
};
