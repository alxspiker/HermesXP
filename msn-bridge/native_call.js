'use strict';
/* Experimental *native* MSN Computer Call endpoint.
 *
 * The bot processes tunneled SIP INVITE/BYE over MSN UUN/UBN and receives
 * bidirectional PCMU (G.711 u-law) RTP on UDP. Media is streamed into the
 * authenticated loopback Hermes Talk adapter. Talk owns ALL voice providers,
 * authentication, realtime conversation, and Hermes tool delegation.
 * No audio capture, extra program, or call UI runs on XP.
 *
 * Transport caveat: WLM 2009 has several proprietary SIP tunnel variants.
 * The known UUN/UBN plain-SIP format is implemented; unknown envelopes are
 * rejected rather than pretending calls have been answered. An actual WLM
 * call trace is necessary to verify this interoperability.
 */
const dgram = require('dgram');
const crypto = require('crypto');
const net = require('net');
const {performance} = require('perf_hooks');

const DEFAULT_PORT = 19740;
const MAX_CALL_MS = 30 * 60 * 1000;
const TALK_BRIDGE_PORT = 18771;
const TALK_MAX_FRAME = 256 * 1024;
const TALK_MAX_PENDING = 256 * 1024;
const RTP_PACKET_MS = 20;
const RTP_SAMPLES_PER_PACKET = 160;
const RTP_PREROLL_PACKETS = 4;
// The host's Talk transport and Messenger RTP have independent clocks.
// A real MSN call had 28 playout underflows despite zero LAN packet loss and
// zero RTP clock skips. Prefer smoother playback: 800ms speech preroll.
// Short replies still flush via the existing 250ms stale-tail rule.
const RTP_SPEECH_START_BYTES = 40 * RTP_SAMPLES_PER_PACKET;
const RTP_MAX_CATCHUP_MS = 30;

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
  const aliases = {v:'via',f:'from',t:'to',i:'call-id',l:'content-length',c:'content-type'};
  for (const [alias, full] of Object.entries(aliases)) {
    if (headers[alias] && !headers[full]) headers[full] = headers[alias];
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

// WLM 2009 and aMSN carry SIP on MSNP UUN/UBN type 12 inside a compact
// XML envelope, base64-encoding the entire SIP request/response. This is
// NOT the raw SIP payload used by earlier diagnostic tests.
function decodeNativeSignal(type, payload) {
  if (type !== 12) return null;
  if (!Buffer.isBuffer(payload) || payload.length > 16384) return null;
  const xml = payload.toString('utf8').trim();
  const match = /^<sip\s+([^<>]{1,300})><msg>([A-Za-z0-9+\/=\r\n]+)<\/msg><\/sip>$/.exec(xml);
  if (!match || !/(?:^|\s)e="base64"(?:\s|$)/.test(match[1])) return null;
  // WLM 2009 omits the optional fid="1" present in aMSN's envelope.
  const callMatch = /(?:^|\s)i="([^"<>]{1,200})"(?:\s|$)/.exec(match[1]);
  if (!callMatch || (/(?:^|\s)fid="/.test(match[1]) &&
      !/(?:^|\s)fid="1"(?:\s|$)/.test(match[1]))) return null;
  const encoded = match[2].replace(/\s+/g, '');
  if (encoded.length > 16000 || encoded.length % 4) return null;
  const sip = Buffer.from(encoded, 'base64');
  if (!sip.length || sip.length > 12000 || sip.toString('base64') !== encoded)
    return null;
  return {callId: callMatch[1], sip};
}
function encodeNativeSignal(callId, sip) {
  if (typeof callId !== 'string' || !/^[A-Za-z0-9{}@.\-_:]{1,200}$/.test(callId) ||
      !Buffer.isBuffer(sip) || !sip.length || sip.length > 12000)
    throw new Error('Invalid native SIP call envelope');
  return Buffer.from('<sip e="base64" fid="1" i="' + callId + '"><msg>' +
                     sip.toString('base64') + '</msg></sip>', 'utf8');
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
function pcmuToTalk(ulaw) {
  // 8kHz PCMU -> Talk's 24kHz PCM16. Repetition preserves speech samples
  // without depending on the legacy 16kHz ASR/TTS pipeline.
  const out = Buffer.alloc(ulaw.length * 6);
  for (let i = 0; i < ulaw.length; i++) {
    const sample = ulawDecode(ulaw[i]);
    for (let n = 0; n < 3; n++) out.writeInt16LE(sample, i * 6 + n * 2);
  }
  return out;
}
function talkFrame(type, payload = Buffer.alloc(0)) {
  if (!Buffer.isBuffer(payload) || payload.length + 1 > TALK_MAX_FRAME)
    throw new Error('Invalid Hermes Talk audio frame');
  const header = Buffer.alloc(5);
  header.writeUInt32BE(payload.length + 1, 0);
  header[4] = type.charCodeAt(0);
  return Buffer.concat([header, payload]);
}
function encodeRtp(payload, seq, stamp, ssrc, marker = false) {
  const frame = Buffer.alloc(12 + payload.length);
  frame[0] = 0x80; frame[1] = marker ? 0x80 : 0;
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
    const old = this.call;
    this.call = null; // suppress reentrant callbacks from closing the socket
    if (old?.expiry) clearTimeout(old.expiry);
    if (old?.audioTimer) clearTimeout(old.audioTimer);
    if (old?.statsTimer) clearInterval(old.statsTimer);
    if (old?.talk) {
      this.logCallStats(old, 'final');
    }
    if (old?.talk) old.talk.destroy();
    if (this.rendezvousTimer) clearTimeout(this.rendezvousTimer);
    this.rendezvousTimer = null;
  }
  logCallStats(call, kind = 'periodic') {
    this.logger.info(
      'Messenger RTP %s: incoming=%d missing=%d talk_pcm=%dms played=%dms ' +
      'underflows=%d clock_skips=%d spacing_lt15ms=%d spacing_gt25ms=%d ' +
      'max_gap_ms=%d queued=%dms peak_buffer=%dms interruptions=%d',
      kind, call.incomingFrames || 0, call.incomingLost || 0,
      Math.round(call.outReceivedMs || 0), Math.round(call.outPlayedMs || 0),
      call.outputUnderflows || 0, call.timerSlips || 0,
      call.shortPacketIntervals || 0, call.longPacketIntervals || 0,
      Math.round(call.maxPacketGapMs || 0),
      Math.round((call.output?.length || 0) / 8),
      call.maxBufferedMs || 0, call.interruptions || 0);
  }
  sendSignal(type, payload) {
    this.client.sendNativeSignal(this.owner, type, payload);
  }
  invite() {
    if (this.call) return false;
    const callId = crypto.randomUUID();
    const xp = this.xpHost;
    const local = this.host;
    const sdp = [
      'v=0', 'o=HermesXP 0 0 IN IP4 ' + local, 's=HermesXP Voice',
      'b=CT:99980', 't=0 0', 'm=audio ' + this.port + ' RTP/AVP 0',
      'c=IN IP4 ' + local, 'a=rtpmap:0 PCMU/8000',
      'a=encryption:rejected', '',
    ].join('\r\n');
    const sip = [
      'INVITE sip:' + this.owner + ' SIP/2.0',
      'v: SIP/2.0/TCP ' + local + ':19740',
      'Max-Forwards: 70',
      'f: <sip:' + this.client.email + '>;tag=hermesxp',
      't: <sip:' + this.owner + '>',
      'i: ' + callId,
      'CSeq: 1 INVITE',
      'm: <sip:' + this.client.email + '>;proxy=replace',
      'Ms-Conversation-ID: f=1',
      'User-Agent: HermesXP-Native/0.2',
      'c: application/sdp',
      'l: ' + Buffer.byteLength(sdp),
      '', sdp,
    ].join('\r\n');
      this.call = {
      id: callId, remote: null, type:12, seq:0,
      stamp:crypto.randomBytes(4).readUInt32BE(0),
      ssrc:crypto.randomBytes(4).readUInt32BE(0),
      initiated: true,
    };
    this.call.expiry = setTimeout(()=>this.closeCall(),MAX_CALL_MS);
    try {
      this.sendSignal(12, encodeNativeSignal(callId, Buffer.from(sip)));
    }catch(e){this.closeCall();throw e;}
    this.logger.info('Sent native MSN tunneled SIP invitation');
    return true;
  }
  hangup() {
    const call = this.call;
    if (!call) return false;
    if (call.remote || call.initiated) {
      const bye = [
        'BYE sip:' + this.owner + ' SIP/2.0',
        'v: SIP/2.0/TCP ' + this.host + ':19740',
        'Max-Forwards: 70',
        'f: <sip:' + this.client.email + '>;tag=hermesxp',
        't: ' + (call.remoteTo || '<sip:' + this.owner + '>'),
        'i: ' + call.id,
        'CSeq: 2 BYE',
        'User-Agent: HermesXP-Native/0.2',
        'l: 0', '', '',
      ].join('\r\n');
      try { this.sendSignal(12, encodeNativeSignal(call.id, Buffer.from(bye))); }
      catch (error) { this.logger.warn('Native call hangup signaling failed:',error.message); }
    }
    this.closeCall();
    return true;
  }
  onSignal({sender, type, payload}) {
    if (sender !== this.owner) return;
    // Type 11 carries rendezvous negotiation metadata; it isn't SIP. WLM
    // sends e.g. "1 3 7 <AppVersion> 0 3 0" before a real call.
    if (type === 11) {
      this.logger.info('Native MSN call rendezvous metadata received');
      const notice = payload.toString('ascii');
      const match = /^1 3 7 ([0-9]{6,10}) 0 3 0$/.exec(notice);
      if (match && !this.call) {
        // WLM requests peer media capability negotiation before its tunneled
        // SIP INVITE. aMSN traces document its matching rendezvous reply
        // shape ("2 3 5 <AppVersion> 0 3 0"). Keep it owner/IP restricted
        // and bounded; this is not yet a proven WLM-originated call fix.
        const now = Date.now();
        if (!this.lastRendezvousAt || now - this.lastRendezvousAt > 2500) {
          this.lastRendezvousAt = now;
          this.sendSignal(11, Buffer.from('2 3 5 ' + match[1] + ' 0 3 0'));
          this.logger.info('Replied to native WLM call rendezvous');
          // Original WLM 2009 outgoing Call still depends on an unimplemented
          // Escargot VOIP service and may show 0x80EE00C8. Offer a *native
          // reciprocal SIP call* instead: its Accept prompt and microphone/
          // speaker stream remain entirely inside Windows Live Messenger.
          this.rendezvousTimer = setTimeout(() => {
            this.rendezvousTimer = null;
            if (!this.call) {
              try { this.invite(); }
              catch(error) {
                this.logger.warn('WLM reciprocal native invitation failed:',error.message);
              }
            }
          }, 650);
        }
      }
      return;
    }
    const inner = decodeNativeSignal(type, payload);
    const sip = inner && parseSip(inner.sip);
    if (!sip) {
      if (process.env.MSN_NATIVE_TRACE === '1') {
        // Explicitly opt-in local-only diagnostic. Hex is bounded and may
        // contain call metadata; never enable in normal service operation.
        this.logger.warn('Native MSN signal sample:', type,
                         payload.subarray(0, 128).toString('hex'));
      }
      this.logger.warn('Native MSN signaling envelope not recognized (type, bytes):',
                       type, payload.length);
      return;
    }
    if (sip.headers['call-id'] !== inner.callId) return;
    const answer = (code, reason, sdp = '') =>
      this.sendSignal(type, encodeNativeSignal(inner.callId, sipResponse(sip, code, reason, sdp)));
    const verb = sip.start.split(' ')[0];
    if (verb === 'SIP/2.0' && this.call &&
        this.call.id === inner.callId && this.call.initiated) {
      const code = Number(sip.start.split(' ')[1]);
      if (code >= 200 && sip.headers.cseq.toUpperCase().includes('INVITE')) {
        // SIP INVITE completes only after ACK. WLM will not start the RTP
        // media leg when it never sees the ACK to its 200 OK.
        const ack = [
          'ACK sip:' + this.owner + ' SIP/2.0',
          'v: SIP/2.0/TCP ' + this.host + ':19740',
          'Max-Forwards: 70',
          'f: <sip:' + this.client.email + '>;tag=hermesxp',
          't: ' + sip.headers.to,
          'i: ' + inner.callId,
          'CSeq: 1 ACK',
          'User-Agent: HermesXP-Native/0.2',
          'l: 0', '', '',
        ].join('\r\n');
        this.sendSignal(12, encodeNativeSignal(inner.callId, Buffer.from(ack)));
      }
      if (code >= 300) {
        this.logger.warn('Messenger declined SIP call:', code);
        this.closeCall();
        return;
      }
      if (code === 200) {
        if (process.env.MSN_NATIVE_TRACE === '1') {
          const diagnostic = sip.body.split(/\r?\n/).filter(x =>
            /^(m=audio|c=IN IP4|a=ice-|a=candidate|a=rtpmap)/.test(x)).slice(0,15);
          this.logger.info('WLM native SDP media descriptors:', diagnostic.join(' | ').slice(0,1200));
        }
        const remote = parseSdp(sip.body);
        if (!remote || remote.ip !== this.xpHost) {
          this.closeCall();return;
        }
        this.call.remote = remote;
        this.call.remoteTo = sip.headers.to;
        this.logger.info('Windows Live Messenger accepted native SIP call; RTP peer port',remote.port);
        this.startTalk(this.call);
      }
      return;
    }
    if (verb === 'INVITE') {
      if (this.call) {
        answer(486, 'Busy Here');
        return;
      }
      const offer = parseSdp(sip.body);
      // This project is LAN-only. Reject a different or public RTP address
      // rather than sending audio to an untrusted network endpoint.
      if (!offer || offer.ip !== this.xpHost) {
        answer(488, 'Not Acceptable Here');
        return;
      }
      const session = {
        id: sip.headers['call-id'], remote: offer, type, seq: 0,
        remoteTo: sip.headers.from,
        stamp: crypto.randomBytes(4).readUInt32BE(0),
        ssrc: crypto.randomBytes(4).readUInt32BE(0),
      };
      const offerAnswer = [
        'v=0', 'o=HermesXP 0 0 IN IP4 ' + this.host, 's=HermesXP',
        'c=IN IP4 ' + this.host, 't=0 0',
        'm=audio ' + this.port + ' RTP/AVP 0',
        'a=rtpmap:0 PCMU/8000', 'a=ptime:20', 'a=sendrecv', '',
      ].join('\r\n');
      this.call = session;
      session.expiry = setTimeout(() => this.closeCall(), MAX_CALL_MS);
      answer(200, 'OK', offerAnswer);
      this.logger.info('Hermes accepted native MSN SIP audio invitation');
      return;
    }
    if ((verb === 'BYE' || verb === 'CANCEL') && this.call &&
        sip.headers['call-id'] === this.call.id) {
      answer(200, 'OK');
      this.closeCall();
      this.logger.info('Hermes native MSN call ended');
      return;
    }
    if (verb === 'ACK') {
      if (this.call && this.call.id === inner.callId &&
          this.call.remote && !this.call.talk)
        this.startTalk(this.call);
      return;
    }
  }
  onRtp(frame, info) {
    const call = this.call;
    if (!call || !call.remote || info.address !== call.remote.ip ||
        info.port !== call.remote.port)
      return;
    const payload = parseRtp(frame);
    if (!payload || payload.length > 1280) return;
    if (!call.rtpSeen) {
      call.rtpSeen = true;
      this.logger.info('First native Messenger PCMU RTP audio frame received');
    }
    // Stop duplicates and re-ordered UDP frames from reaching Talk as
    // repeated microphone samples. A gap remains an acoustic gap, never
    // duplicated fake speech.
    const seq = frame.readUInt16BE(2);
    if (call.inputSeq !== undefined) {
      const advance = (seq - call.inputSeq + 65536) & 65535;
      if (advance === 0 || advance >= 32768) return;
      if (advance > 1) call.incomingLost = (call.incomingLost || 0) + advance - 1;
    }
    call.inputSeq = seq;
    call.incomingFrames = (call.incomingFrames || 0) + 1;
    if (call.talkReady && call.talk && !call.talk.destroyed &&
        call.talk.writableLength < TALK_MAX_PENDING)
      call.talk.write(talkFrame('I', pcmuToTalk(payload)));
  }
  startTalk(call) {
    if (this.call !== call || call.talk) return;
    call.talkIncoming = Buffer.alloc(0);
    call.talkRemainder = Buffer.alloc(0);
    call.output = Buffer.alloc(0);
    call.readyAt = 0;
    call.outSpeaking = false;
    call.packetAt = performance.now() + RTP_PACKET_MS;
    call.lastPacketSentAt = null;
    call.shortPacketIntervals = 0;
    call.longPacketIntervals = 0;
    call.maxPacketGapMs = 0;
    call.outputUnderflows = 0;
    call.timerSlips = 0;
    call.incomingLost = 0;
    call.incomingFrames = 0;
    call.outReceivedMs = 0;
    call.outPlayedMs = 0;
    call.maxBufferedMs = 0;
    call.interruptions = 0;
    this.scheduleTalkAudio(call);
    // WLM 2009 does not always deliver SIP BYE when its call window closes.
    // Periodic content-free stats remain available even if the call outlives
    // its GUI. No microphone PCM or transcript content is logged.
    call.statsTimer = setInterval(() => {
      if (this.call === call && call.rtpSeen)
        this.logCallStats(call);
    }, 12000);
    const connection = net.connect({host: '127.0.0.1', port: TALK_BRIDGE_PORT});
    call.talk = connection;
    connection.on('connect', () => {
      if (this.call === call)
        connection.write(talkFrame('H', Buffer.from(JSON.stringify({token: this.token}))));
    });
    connection.on('data', chunk => this.onTalkData(call, chunk));
    connection.on('error', error => {
      if (this.call === call)
        this.logger.warn('Hermes Talk audio bridge unavailable:', error.code || error.message);
    });
    connection.on('close', () => {
      if (this.call === call) {
        this.logger.warn('Hermes Talk audio session closed; ending MSN call');
        this.hangup();
      }
    });
    this.logger.info('Starting MSN audio through Hermes Talk plugin');
  }
  onTalkData(call, chunk) {
    if (this.call !== call) return;
    call.talkIncoming = Buffer.concat([call.talkIncoming, chunk]);
    if (call.talkIncoming.length > TALK_MAX_FRAME * 2) {
      call.talk.destroy();return;
    }
    while (call.talkIncoming.length >= 5) {
      const len = call.talkIncoming.readUInt32BE(0);
      if (len < 1 || len > TALK_MAX_FRAME) {call.talk.destroy();return;}
      if (call.talkIncoming.length < 4 + len) return;
      const type = String.fromCharCode(call.talkIncoming[4]);
      const payload = call.talkIncoming.subarray(5, 4 + len);
      call.talkIncoming = call.talkIncoming.subarray(4 + len);
      if (type === 'R') {
        call.talkReady = true;
        this.logger.info('Hermes Talk PCM bridge ready');
      } else if (type === 'D') {
        // Hermes Talk owns interruption/truncation decisions.
        call.interruptions = (call.interruptions || 0) + 1;
        call.output = Buffer.alloc(0);
        call.talkRemainder = Buffer.alloc(0);
        call.outSpeaking = false;
        call.lastOutputAt = 0;
      } else if (type === 'X') {
        this.logger.warn('Hermes Talk rejected native call (%s)',
                         payload.toString('ascii').slice(0, 100));
        call.talk.destroy();
      } else if (type === 'O') {
        // Incoming Talk audio is PCM16/24000, not the old 16kHz worker WAV.
        const combined = Buffer.concat([call.talkRemainder, payload]);
        const samples = Math.floor(combined.length / 6);
        const compressed = Buffer.alloc(samples);
        for (let i = 0; i < samples; i++) {
          const offset = i * 6;
          const a = combined.readInt16LE(offset);
          const b = combined.readInt16LE(offset + 2);
          const c = combined.readInt16LE(offset + 4);
          compressed[i] = ulawEncode(Math.round((a + b + c) / 3));
        }
        call.talkRemainder = combined.subarray(samples * 6);
        call.output = Buffer.concat([call.output, compressed]);
        call.outReceivedMs += compressed.length / 8;
        call.maxBufferedMs = Math.max(
          call.maxBufferedMs, Math.round(call.output.length / 8));
        call.lastOutputAt = performance.now();
        if (call.output.length > 16000) {
          // Bounded ~2s maximum, keep newest audio rather than playing old
          // speech late if XP cannot keep up with a provider's streaming rate.
          call.droppedAudioBytes = (call.droppedAudioBytes || 0) +
            (call.output.length - 16000);
          call.output = call.output.subarray(call.output.length - 16000);
          // Flooding the journal itself once caused additional event-loop
          // delays and more choppy RTP. Report a bounded summary instead.
          if (!call.lastOverflowReport || Date.now() - call.lastOverflowReport >= 2000) {
            this.logger.warn('Hermes Talk RTP audio backlog; dropped %d bytes since last report',
                             call.droppedAudioBytes);
            call.droppedAudioBytes = 0;
            call.lastOverflowReport = Date.now();
          }
        }
      } else {call.talk.destroy();return;}
    }
  }
  scheduleTalkAudio(call) {
    if (this.call !== call) return;
    // The previous 10ms polling timer sometimes delivered two 20ms RTP
    // packets less than 15ms apart even while clock_skips stayed zero. WLM's
    // legacy jitter buffer can interpret these as bursty audio. Schedule
    // directly against the next monotonic packet deadline instead of
    // polling for it with a second, unrelated clock.
    const delay = call.remote
      ? Math.max(1, call.packetAt - performance.now())
      : RTP_PACKET_MS;
    call.audioTimer = setTimeout(() => {
      if (this.call !== call) return;
      this.tickTalkAudio(call);
      this.scheduleTalkAudio(call);
    }, delay);
  }
  tickTalkAudio(call) {
    if (this.call !== call || !call.remote) return;
    const now = performance.now();
    // Old Messenger jitter buffers dislike 2-3 back-to-back RTP packets.
    // After a scheduler stall, advance the RTP clock over missed time rather
    // than flooding the receiver with a compressed catch-up burst.
    if (now - call.packetAt > RTP_MAX_CATCHUP_MS) {
      const missed = Math.max(1, Math.floor((now - call.packetAt) / RTP_PACKET_MS));
      call.stamp = (call.stamp + missed * RTP_SAMPLES_PER_PACKET) >>> 0;
      call.packetAt += missed * RTP_PACKET_MS;
      call.timerSlips = (call.timerSlips || 0) + missed;
    }
    if (call.packetAt > now + 1) return;
    const buffered = call.output.length;
    const staleShortReply = buffered >= 160 && call.lastOutputAt &&
      now - call.lastOutputAt > 250;
    let marker = false;
    let out;
    if (buffered >= 160 &&
        (call.outSpeaking || buffered >= RTP_SPEECH_START_BYTES || staleShortReply)) {
      out = call.output.subarray(0, 160);
      call.output = call.output.subarray(160);
      if (!call.outSpeaking) {marker = true; call.outSpeaking = true;}
      call.outPlayedMs = (call.outPlayedMs || 0) + RTP_PACKET_MS;
    } else {
      out = Buffer.alloc(160, 0xff);
      if (call.outSpeaking) {
        call.outputUnderflows = (call.outputUnderflows || 0) + 1;
        // A 20-100ms provider/OS gap is not the end of an utterance. If we
        // reset on each missing frame, the new 800ms jitter-buffer preroll
        // is paid REPEATEDLY mid-sentence: this is audible as chopped words.
        // Stay in the speech phase across short gaps; do not invent samples.
        if (!call.lastOutputAt || now - call.lastOutputAt > 550)
          call.outSpeaking = false;
      }
    }
    const packet = encodeRtp(out, call.seq++, call.stamp, call.ssrc, marker);
    call.stamp = (call.stamp + RTP_SAMPLES_PER_PACKET) >>> 0;
    this.sock.send(packet, call.remote.port, call.remote.ip);
    if (call.lastPacketSentAt != null) {
      const gap = now - call.lastPacketSentAt;
      if (gap < 15) call.shortPacketIntervals = (call.shortPacketIntervals || 0) + 1;
      if (gap > 25) call.longPacketIntervals = (call.longPacketIntervals || 0) + 1;
      call.maxPacketGapMs = Math.max(call.maxPacketGapMs || 0, gap);
    }
    call.lastPacketSentAt = now;
    call.packetAt += RTP_PACKET_MS;
  }
}

module.exports = {
  NativeCall, parseSip, parseSdp, sipResponse, parseRtp, encodeRtp,
  ulawEncode, ulawDecode, resamplePcm8To16, pcmuToTalk, talkFrame,
  encodeNativeSignal, decodeNativeSignal,
};
