'use strict';
/* Experimental *native* MSN Computer Call endpoint.
 *
 * The bot processes tunneled SIP INVITE/BYE over MSN UUN/UBN and receives
 * bidirectional PCMU (G.711 u-law) RTP on UDP. Media is handed to the same
 * loopback-only local Hermes speech/agent worker used by the XP companion.
 * No audio capture, extra program, or call UI runs on XP.
 *
 * Transport caveat: WLM 2009 has several proprietary SIP tunnel variants.
 * The known UUN/UBN plain-SIP format is implemented; unknown envelopes are
 * rejected rather than pretending calls have been answered. An actual WLM
 * call trace is necessary to verify this interoperability.
 */
const dgram = require('dgram');
const crypto = require('crypto');
const http = require('http');
const net = require('net');

const DEFAULT_PORT = 19740;
const MAX_CALL_MS = 30 * 60 * 1000;
const MAX_RECORD_BYTES = 8000 * 2 * 25;
const SILENCE_MS = 700;
const MIN_TALK_MS = 220;
const MAX_TALK_MS = 24000;
const AUDIO_WORKER_PORT = 18771;

function parseSip(data) {
  if (!Buffer.isBuffer(data) || data.length > 16384 || !data.length) return null;
  const split = data.indexOf('\r\n\r\n');
  if (split < 0) return null;
  const head = data.subarray(0, split).toString('utf8').split('\r\n');
  if (!/^(INVITE|ACK|BYE|CANCEL|SIP\/2\.0)\b/.test(head[0])) return null;
  const headers = {};
  for (const line of head.slice(1)) {
    const colon = line.indexOf(':');
    if (colon <= 0 || colon > 60 || line.length > 2048) return null;
    const key = line.slice(0, colon).toLowerCase();
    const value = line.slice(colon + 1).trim();
    if (!headers[key]) headers[key] = value;
  }
  if (!headers['call-id'] || !headers.cseq || !headers.from || !headers.to ||
      !headers.via || headers['call-id'].length > 200) return null;
  const rawLength = headers['content-length'];
  if (rawLength && (!/^\d{1,5}$/.test(rawLength) ||
      Number(rawLength) > data.length - split - 4)) return null;
  return {
    start: head[0], headers,
    body: data.subarray(split + 4, rawLength === undefined ?
                        undefined : split + 4 + Number(rawLength)).toString('utf8'),
  };
}

function parseSdp(sdp) {
  if (typeof sdp !== 'string' || sdp.length > 8192) return null;
  const connection = sdp.match(/^c=IN IP4 (\d+\.\d+\.\d+\.\d+)\s*$/m);
  const audio = sdp.match(/^m=audio (\d{1,5}) RTP\/AVP ([\d ]+)\s*$/m);
  if (!connection || !audio || net.isIP(connection[1]) !== 4) return null;
  const port = Number(audio[1]);
  if (port < 1024 || port > 65535) return null;
  const codecs = audio[2].trim().split(/\s+/).map(Number);
  const codec = codecs.includes(0) ? 0 : null;
  if (codec === null) return null;
  return {ip: connection[1], port, codec};
}

function sipResponse(request, code, status, sdp = '') {
  const h = request.headers;
  // Copy request transaction identity; do not emit arbitrary unbounded
  // values from untrusted SIP input.
  const tag = ';tag=hermesxp';
  const to = h.to.includes(';tag=') ? h.to : h.to + tag;
  const response = [
    'SIP/2.0 ' + code + ' ' + status,
    'Via: ' + h.via,
    'From: ' + h.from,
    'To: ' + to,
    'Call-ID: ' + h['call-id'],
    'CSeq: ' + h.cseq,
    'User-Agent: HermesXP-Native/0.1',
    ...(sdp ? ['Content-Type: application/sdp'] : []),
    'Content-Length: ' + Buffer.byteLength(sdp),
    '', sdp,
  ].join('\r\n');
  return Buffer.from(response, 'utf8');
}

// G.711 PCMU, RTP payload type 0. No lossy transcoding dependencies.
function ulawDecode(value) {
  const u = (~value) & 255;
  const magnitude = (((u & 15) << 3) + 132) << ((u >> 4) & 7);
  return (u & 128) ? (132 - magnitude) : (magnitude - 132);
}
function ulawEncode(sample) {
  const sign = sample < 0 ? 128 : 0;
  const v = Math.min(32635, Math.abs(sample)) + 132;
  let exponent = 7;
  for (let mask = 0x4000; (v & mask) === 0 && exponent > 0; mask >>= 1)
    exponent--;
  const mantissa = (v >> (exponent + 3)) & 15;
  return (~(sign | (exponent << 4) | mantissa)) & 255;
}
function resamplePcm8To16(ulaw) {
  // Nearest-neighbor 2x is sufficient for speech recognition; 16k WAV.
  const result = Buffer.alloc(ulaw.length * 4);
  for (let i = 0; i < ulaw.length; i++) {
    const sample = ulawDecode(ulaw[i]);
    result.writeInt16LE(sample, i * 4);
    result.writeInt16LE(sample, i * 4 + 2);
  }
  return result;
}
function encodeRtp(payload, seq, stamp, ssrc) {
  const frame = Buffer.alloc(12 + payload.length);
  frame[0] = 0x80; frame[1] = 0;
  frame.writeUInt16BE(seq & 0xffff, 2);
  frame.writeUInt32BE(stamp >>> 0, 4);
  frame.writeUInt32BE(ssrc >>> 0, 8);
  payload.copy(frame, 12);
  return frame;
}
function parseRtp(datagram) {
  if (datagram.length < 12 || (datagram[0] >> 6) !== 2) return null;
  const cc = datagram[0] & 15;
  let offset = 12 + cc * 4;
  if (datagram[0] & 0x10) {
    if (offset + 4 > datagram.length) return null;
    offset += 4 + datagram.readUInt16BE(offset + 2) * 4;
  }
  if (offset > datagram.length || (datagram[1] & 0x7f) !== 0) return null;
  let end = datagram.length;
  if (datagram[0] & 0x20) end -= datagram[end - 1];
  if (end <= offset) return null;
  return datagram.subarray(offset, end);
}

function requestWorker(token, method, route, body = Buffer.alloc(0)) {
  return new Promise((resolve, reject) => {
    if (!token || token.length < 32) return reject(new Error('native worker credential missing'));
    const req = http.request({
      host: '127.0.0.1', port: AUDIO_WORKER_PORT,
      method, path: route, timeout: 12000,
      headers: {'X-Hermes-Token': token, 'Content-Type': 'application/octet-stream',
                'Content-Length': body.length},
    }, res => {
      const buffers = [];
      let length = 0;
      res.on('data', part => {
        length += part.length;
        if (length > 1_500_000) return req.destroy(new Error('native speech response too large'));
        buffers.push(part);
      });
      res.on('end', () => resolve({code: res.statusCode, body: Buffer.concat(buffers)}));
    });
    req.on('timeout', () => req.destroy(new Error('native worker timed out')));
    req.on('error', reject);
    req.end(body);
  });
}

class NativeCall {
  constructor({client, owner, host, xpHost, token, port = DEFAULT_PORT, logger = console}) {
    if (net.isIP(host) !== 4 || net.isIP(xpHost) !== 4)
      throw new Error('native call requires concrete host and XP IPv4 addresses');
    this.client = client;
    this.owner = owner;
    this.host = host;
    this.xpHost = xpHost;
    this.token = token;
    this.port = port;
    this.logger = logger;
    this.sock = dgram.createSocket('udp4');
    this.call = null;
    this.sending = false;
    this.sock.on('message', (bytes, info) => this.onRtp(bytes, info));
    this.sock.on('error', err => {
      this.logger.error('Native RTP socket error:', err.message);
      this.closeCall();
    });
  }
  start() {
    this.sock.bind(this.port, this.host);
  }
  stop() {
    this.closeCall();
    this.sock.close();
  }
  closeCall() {
    if (this.call?.expiry) clearTimeout(this.call.expiry);
    this.call = null;
  }
  sendSignal(type, payload) {
    this.client.sendNativeSignal(this.owner, type, payload);
  }
  onSignal({sender, type, payload}) {
    if (sender !== this.owner) return;
    const sip = parseSip(payload);
    if (!sip) {
      this.logger.warn('Native MSN signaling envelope not recognized (type, bytes):',
                       type, payload.length);
      return;
    }
    const verb = sip.start.split(' ')[0];
    if (verb === 'INVITE') {
      if (this.call) {
        this.sendSignal(type, sipResponse(sip, 486, 'Busy Here'));
        return;
      }
      const offer = parseSdp(sip.body);
      // This project is LAN-only. Reject a different or public RTP address
      // rather than sending audio to an untrusted network endpoint.
      if (!offer || offer.ip !== this.xpHost) {
        this.sendSignal(type, sipResponse(sip, 488, 'Not Acceptable Here'));
        return;
      }
      const session = {
        id: sip.headers['call-id'], remote: offer, type, seq: 0,
        stamp: crypto.randomBytes(4).readUInt32BE(0),
        ssrc: crypto.randomBytes(4).readUInt32BE(0),
        chunks: [], bytes: 0, voicedMs: 0, quietMs: 0, busy: false,
      };
      const offerAnswer = [
        'v=0', 'o=HermesXP 0 0 IN IP4 ' + this.host, 's=HermesXP',
        'c=IN IP4 ' + this.host, 't=0 0',
        'm=audio ' + this.port + ' RTP/AVP 0',
        'a=rtpmap:0 PCMU/8000', 'a=ptime:20', 'a=sendrecv', '',
      ].join('\r\n');
      this.call = session;
      session.expiry = setTimeout(() => this.closeCall(), MAX_CALL_MS);
      this.sendSignal(type, sipResponse(sip, 200, 'OK', offerAnswer));
      this.logger.info('Hermes accepted native MSN SIP audio invitation');
      return;
    }
    if ((verb === 'BYE' || verb === 'CANCEL') && this.call &&
        sip.headers['call-id'] === this.call.id) {
      this.sendSignal(type, sipResponse(sip, 200, 'OK'));
      this.closeCall();
      this.logger.info('Hermes native MSN call ended');
      return;
    }
    if (verb === 'ACK') return;
  }
  onRtp(frame, info) {
    const call = this.call;
    if (!call || info.address !== call.remote.ip || info.port !== call.remote.port ||
        call.busy) return;
    const payload = parseRtp(frame);
    if (!payload || payload.length > 1280) return;
    let peak = 0;
    for (const sample of payload) {
      const a = Math.abs(ulawDecode(sample));
      if (a > peak) peak = a;
    }
    const duration = payload.length / 8;
    if (peak > 600) {
      call.voicedMs += duration;
      call.quietMs = 0;
    } else if (call.voicedMs >= MIN_TALK_MS) {
      call.quietMs += duration;
    }
    if (call.bytes + payload.length * 4 <= MAX_RECORD_BYTES) {
      call.chunks.push(resamplePcm8To16(payload));
      call.bytes += payload.length * 4;
    }
    if ((call.voicedMs >= MIN_TALK_MS && call.quietMs >= SILENCE_MS) ||
        (call.bytes >= MAX_RECORD_BYTES) || call.voicedMs > MAX_TALK_MS) {
      const pcm = Buffer.concat(call.chunks);
      call.chunks = []; call.bytes = 0; call.voicedMs = 0; call.quietMs = 0;
      call.busy = true;
      this.processTurn(call, pcm).catch(err => {
        this.logger.warn('Native voice turn failed:', err.message);
      }).finally(() => {
        if (this.call === call) call.busy = false;
      });
    }
  }
  async processTurn(call, pcm) {
    const started = await requestWorker(this.token, 'POST', '/voice/turn', pcm);
    if (started.code !== 202) throw new Error('speech worker rejected native turn');
    const turnId = started.body.toString('ascii');
    if (!/^[0-9a-f]{24}$/.test(turnId)) throw new Error('invalid speech turn id');
    let response;
    for (let n = 0; n < 240; n++) {
      if (this.call !== call) return;
      await new Promise(resolve => setTimeout(resolve, 1000));
      response = await requestWorker(this.token, 'GET', '/voice/turn/' + turnId);
      if (response.code !== 202) break;
    }
    if (!response || response.code !== 200 || this.call !== call)
      throw new Error('native voice worker did not return audio');
    await this.playPcm16(call, response.body);
  }
  async playPcm16(call, pcm) {
    // Speech worker outputs 16kHz PCM16; 2:1 downsample to 8kHz for PCMU.
    for (let offset = 0; offset + 640 <= pcm.length; offset += 640) {
      if (this.call !== call) return;
      const chunk = Buffer.alloc(160);
      for (let i = 0; i < 160; i++)
        chunk[i] = ulawEncode(pcm.readInt16LE(offset + i * 4));
      const rtp = encodeRtp(chunk, call.seq++, call.stamp, call.ssrc);
      call.stamp = (call.stamp + 160) >>> 0;
      this.sock.send(rtp, call.remote.port, call.remote.ip);
      await new Promise(resolve => setTimeout(resolve, 20));
    }
  }
}

module.exports = {
  NativeCall, parseSip, parseSdp, sipResponse, parseRtp, encodeRtp,
  ulawEncode, ulawDecode, resamplePcm8To16, requestWorker,
};
