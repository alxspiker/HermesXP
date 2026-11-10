"""Binary MSNP/UUN framing and native SIP/RTP interoperability unit tests."""
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeCallTests(unittest.TestCase):
    def run_js(self, source):
        result = subprocess.run(
            ["node", "-e", source], cwd=ROOT / "msn-bridge",
            text=True, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_fragmented_msnp13_ubn_binary_payload(self):
        self.run_js(r"""
const assert = require('assert');
const {MSNPFrameDecoder} = require('./msnclient/frame.js');
const d = new MSNPFrameDecoder();
const body = Buffer.from('INVITE sip:bot@hermes.local SIP/2.0\r\nX: a\r\n\r\n\0AB', 'binary');
const frame = Buffer.concat([Buffer.from('UBN user@hermes.local 1 ' +
  body.length + '\r\n'), body, Buffer.from('UUN 24 OK\r\n')]);
assert.equal(d.feed(frame.subarray(0, 4)).length, 0);
assert.equal(d.feed(frame.subarray(4, 15)).length, 0);
const messages = d.feed(frame.subarray(15));
assert.equal(messages.length, 2);
assert.equal(messages[0].command, 'UBN');
assert.deepEqual(messages[0].body, body);
assert.equal(messages[1].command, 'UUN');
assert.equal(d.pending.length, 0);
assert.throws(() => d.feed(Buffer.from('UBN user 1 999999\r\n')));
const presence = Buffer.from('<Data><PSM>hello</PSM></Data>');
const ubx = Buffer.concat([Buffer.from('UBX 1:peer@example.test ' +
  presence.length + '\r\n'), presence,
  Buffer.from('RNG 42 127.0.0.1:1864 CKI 123 peer@example.test\r\n')]);
const parsed = new MSNPFrameDecoder().feed(ubx);
assert.equal(parsed.length,2);
assert.deepEqual(parsed[0].body,presence);
assert.equal(parsed[1].command,'RNG');
""")

    def test_msnp_stream_boundary_conformance(self):
        self.run_js(r"""
const assert = require('assert');
const {MSNPFrameDecoder} = require('./msnclient/frame.js');
const binary = Buffer.from([0, 13, 10, 255, 65, 66]);
const presence = Buffer.from('<Data><PSM>hi</PSM></Data>');
function frame(command, header, body) {
  return Buffer.concat([Buffer.from(command + ' ' + header + ' ' + body.length + '\r\n'), body]);
}
const examples = [
  frame('UBN', 'peer@example.test 1', binary),
  frame('UBX', '1:peer@example.test', presence),
  frame('UUN', '23 peer@example.test 12', Buffer.from('INVITE\r\n\0SIP')),
];
for (const bytes of examples) {
  const expectedBody = bytes.subarray(bytes.indexOf(Buffer.from('\r\n')) + 2);
  for (let split = 0; split <= bytes.length; split++) {
    const decoder = new MSNPFrameDecoder();
    const first = decoder.feed(bytes.subarray(0, split));
    if (split < bytes.length) assert.deepEqual(first, [], 'premature frame at split ' + split);
    const decoded = first.length ? first : decoder.feed(bytes.subarray(split));
    assert.equal(decoded.length, 1, 'frame count at split ' + split);
    assert.deepEqual(decoded[0].body, expectedBody, 'body at split ' + split);
    assert.equal(decoder.pending.length, 0);
  }
}
const bytewise = new MSNPFrameDecoder();
const joined = Buffer.concat([examples[0], Buffer.from('UUN 24 OK\r\n'), examples[1]]);
let parsed = [];
for (const byte of joined) parsed.push(...bytewise.feed(Buffer.from([byte])));
assert.equal(parsed.length, 3);
assert.deepEqual(parsed[0].body, binary);
assert.deepEqual(parsed[1].body, Buffer.alloc(0));
assert.deepEqual(parsed[2].body, presence);
const coalesced = new MSNPFrameDecoder().feed(joined);
assert.equal(coalesced.length, 3);
assert.deepEqual(coalesced.map(item => item.command), ['UBN', 'UUN', 'UBX']);
assert.throws(() => new MSNPFrameDecoder().feed(Buffer.from('UBX 1:peer nope\r\n')), /Invalid MSNP payload length/);
assert.throws(() => new MSNPFrameDecoder().feed(Buffer.from('UBX 1:peer 65537\r\n')), /Invalid MSNP payload length|exceeds size limit/);
assert.throws(() => new MSNPFrameDecoder().feed(Buffer.alloc(67585, 65)), /exceeds bounded buffer|incomplete frame exceeds size limit/);
""");

    def test_msnp18_sso_rps_key_derivation(self):
        self.run_js(r"""
const assert = require('assert');
const {rpsKey,signChallenge} = require('./msnclient/sso.js');
const key=Buffer.alloc(24,1);
const result=rpsKey(key,Buffer.from('WS-SecureConversationSESSION KEY HASH'));
assert.equal(result.toString('hex'),'454c4f56ed426848d668efe858daf483520696b91a5888a3');
const proof=signChallenge(key.toString('base64'),Buffer.alloc(48,3).toString('base64'));
const binary=Buffer.from(proof,'base64');
assert.equal(binary.readUInt32LE(0),28);
assert.equal(binary.readUInt32LE(12),0x8004);
assert.equal(binary.readUInt32LE(16),8);
assert.equal(binary.readUInt32LE(20),20);
assert.equal(binary.length,28+8+20+binary.readUInt32LE(24));
""")

    def test_sip_sdp_offer_accept_and_reject(self):
        self.run_js(r"""
const assert = require('assert');
const {
  parseSip, parseSdp, sipResponse, NativeCall, encodeNativeSignal, decodeNativeSignal
} = require('./native_call.js');
const offer = 'v=0\r\no=user 0 0 IN IP4 192.168.1.84\r\ns=-\r\nc=IN IP4 192.168.1.84\r\nt=0 0\r\nm=audio 30000 RTP/AVP 112 0 8\r\na=rtpmap:0 PCMU/8000\r\n';
const message = Buffer.from([
  'INVITE sip:bot@hermes.local SIP/2.0',
  'Via: SIP/2.0/UDP 192.168.1.84:5060;branch=z9hABC',
  'From: <sip:user@hermes.local>;tag=abc',
  'To: <sip:bot@hermes.local>',
  'Call-ID: call-a', 'CSeq: 1 INVITE', 'Content-Type: application/sdp',
  'Content-Length: '+Buffer.byteLength(offer), '', offer,
].join('\r\n'));
const parsed = parseSip(message);
assert(parsed);
assert.equal(parsed.headers['call-id'], 'call-a');
assert.equal(parseSdp(parsed.body).port, 30000);
assert.equal(parseSdp(parsed.body).codec, 0);
assert.equal(parseSdp(offer.replace('c=IN IP4 192.168.1.84', 'c=IN IP4 evil.example')), null);
assert.equal(parseSdp(offer.replace('RTP/AVP 112 0 8','RTP/AVP 112 8')), null);
const response = sipResponse(parsed,200,'OK',offer).toString();
assert(response.startsWith('SIP/2.0 200 OK\r\n'));
assert(response.includes('Call-ID: call-a'));
assert(response.includes('To: <sip:bot@hermes.local>;tag=hermesxp'));
assert.equal(parseSip(Buffer.from('junk')), null);
const compact = Buffer.from([
  'INVITE sip:bot@hermes.local SIP/2.0',
  'v: SIP/2.0/TCP 192.168.1.84:5060',
  'f: <sip:user@hermes.local>;tag=abc',
  't: <sip:bot@hermes.local>',
  'i: compact-call', 'CSeq: 1 INVITE', 'l: 0', '', '',
].join('\r\n'));
assert.equal(parseSip(compact).headers['call-id'],'compact-call');
const tunnel = encodeNativeSignal('call-a',message);
assert.deepEqual(decodeNativeSignal(12,tunnel),{callId:'call-a',sip:message});
assert.deepEqual(decodeNativeSignal(12,Buffer.from(tunnel.toString().replace(' fid="1"',''))),
                 {callId:'call-a',sip:message});
assert.equal(decodeNativeSignal(11,Buffer.from('1 3 7 234889141 0 3 0')),null);
assert.equal(decodeNativeSignal(12,Buffer.from('<sip><invalid/></sip>')),null);
const sent = [];
const native = new NativeCall({
  client:{sendNativeSignal:(to,type,data)=>sent.push({to,type,data})},
  owner:'user@hermes.local',host:'127.0.0.1',xpHost:'192.168.1.84',
  token:'x'.repeat(64),logger:{info:()=>{}, warn:()=>{}, error:()=>{}},
});
native.onSignal({sender:'evil@hermes.local',type:12,payload:tunnel});
assert.equal(sent.length,0);
native.onSignal({sender:'user@hermes.local',type:11,payload:Buffer.from('1 3 7 234889141 0 3 0')});
assert.equal(sent.length,1);
assert.equal(sent[0].type,11);
assert.equal(sent[0].data.toString(),'2 3 5 234889141 0 3 0');
native.onSignal({sender:'user@hermes.local',type:12,payload:tunnel});
assert.equal(sent.length,2);
assert.equal(native.call.remote.port,30000);
assert(decodeNativeSignal(sent[1].type,sent[1].data).sip.toString().startsWith('SIP/2.0 200'));
native.onSignal({sender:'user@hermes.local',type:12,payload:tunnel});
assert(decodeNativeSignal(sent[2].type,sent[2].data).sip.toString().startsWith('SIP/2.0 486'));
native.stop();
""")

    def test_native_bot_offer_and_hangup_keep_wlm_as_audio_frontend(self):
        self.run_js(r"""
const assert=require('assert');
const {NativeCall,decodeNativeSignal}=require('./native_call.js');
const sent=[];
const native=new NativeCall({
  client:{email:'hermes-bot@hermes.local',sendNativeSignal:(to,type,body)=>
    sent.push({to,type,body})},
  owner:'user@hermes.local',host:'192.168.1.81',xpHost:'192.168.1.84',
  token:'a'.repeat(64),logger:{info(){},warn(){},error(){}},
});
assert.equal(native.invite(),true);
assert.equal(native.invite(),false);
const offer=decodeNativeSignal(sent[0].type,sent[0].body);
assert(offer.sip.toString().includes('m=audio 19740 RTP/AVP 0'));
assert(!offer.sip.toString().includes('m=video'));
assert.equal(sent[0].to,'user@hermes.local');
assert.equal(native.hangup(),true);
const bye=decodeNativeSignal(sent[1].type,sent[1].body);
assert(bye.sip.toString().startsWith('BYE sip:user@hermes.local SIP/2.0'));
assert.equal(native.hangup(),false);
native.stop();
""")

    def test_messenger_call_toolbar_rendezvous_and_native_end_button(self):
        self.run_js(r"""
const assert=require('assert');
const {NativeCall,decodeNativeSignal,encodeNativeSignal}=require('./native_call.js');
const sent=[],timers=[];
const origTimeout=global.setTimeout;
const origClearTimeout=global.clearTimeout;
global.setTimeout=(fn,delay)=>{const timer={fn,delay,cleared:false};timers.push(timer);return timer;};
global.clearTimeout=t=>{if(t)t.cleared=true;};
const n=new NativeCall({
 client:{email:'bot@hermes.local',
  sendNativeSignal:(to,type,payload)=>sent.push({to,type,payload})},
 owner:'owner@hermes.local',host:'192.168.1.81',
 xpHost:'192.168.1.84',token:'a'.repeat(64),
 logger:{info(){},warn(){},error(){}}
});
try {
 const rendezvous={sender:'owner@hermes.local',type:11,
  payload:Buffer.from('1 3 7 234889141 0 3 0')};
 n.onSignal({...rendezvous,sender:'stranger@hermes.local'});
 assert.equal(sent.length,0,'only the paired owner may initiate a call');
 n.onSignal(rendezvous);
 assert.equal(sent.length,1);
 assert.equal(sent[0].payload.toString(),'2 3 5 234889141 0 3 0');
 assert(timers.some(t=>t.delay===2500));
 n.onSignal(rendezvous);
 assert.equal(sent.length,1,'duplicate button events must not generate duplicate SIP invites');
 const ready=timers.find(t=>t.delay===2500);
 ready.fn();
 assert.equal(sent.length,2);
 const offer=decodeNativeSignal(12,sent[1].payload);
 assert(offer.sip.toString().startsWith('INVITE '));
 assert.equal(n.call.initiated,true);
 // Calling /hangup from the Hermes side must still work.
 assert.equal(n.hangup(),true);
 assert.equal(n.call,null);
 assert.equal(sent.length,3);
 // WLM emits a type-11 rendezvous frame as it tears down a call.
 // It must never produce a redial after that BYE.
 n.lastRendezvousAt=0;
 n.onSignal(rendezvous);
 assert.equal(sent.length,3,'post-hangup rendezvous must not re-invite');
 assert.equal(n.call,null);
 // When Messenger calls again after the guard interval, it should work.
 n.lastCallEndedAt=Date.now()-5000;
 n.onSignal(rendezvous);
 assert.equal(sent.length,4);
 const again=timers.filter(t=>t.delay===2500).at(-1);
 again.fn();
 assert.equal(sent.length,5);
 assert(n.call);
 // WLM End Call sends a SIP BYE. The bot should return 200 and close.
 const callId=n.call.id;
 const bye=[
  'BYE sip:bot@hermes.local SIP/2.0',
  'Via: SIP/2.0/TCP 192.168.1.84:5060',
  'From: <sip:owner@hermes.local>;tag=abc',
  'To: <sip:bot@hermes.local>;tag=def',
  'Call-ID: '+callId,'CSeq: 2 BYE','Content-Length: 0','','',
 ].join('\r\n');
 n.onSignal({sender:'owner@hermes.local',type:12,
  payload:encodeNativeSignal(callId,Buffer.from(bye))});
 assert.equal(n.call,null);
 const answer=decodeNativeSignal(12,sent.at(-1).payload);
 assert(answer.sip.toString().startsWith('SIP/2.0 200 OK'));
 assert.equal(n.hangup(),false,'chat hangup accurately reports no active call');
}finally{n.stop();global.setTimeout=origTimeout;global.clearTimeout=origClearTimeout;}
""")

    def test_messenger_rendezvous_pending_invitation_can_be_cancelled(self):
        self.run_js(r"""
const assert=require('assert');
const {NativeCall}=require('./native_call.js');
const sent=[],timeouts=[];
const oldTimeout=global.setTimeout,oldClear=global.clearTimeout;
global.setTimeout=(fn,ms)=>{const t={fn,ms,cancelled:false};timeouts.push(t);return t;};
global.clearTimeout=t=>{if(t)t.cancelled=true;};
const n=new NativeCall({client:{email:'bot@hermes.local',
 sendNativeSignal:(to,type,p)=>sent.push({type,p})},owner:'owner@hermes.local',
 host:'192.168.1.81',xpHost:'192.168.1.84',
 token:'a'.repeat(64),logger:{info(){},warn(){},error(){}}});
try{
 n.onSignal({sender:'owner@hermes.local',type:11,
   payload:Buffer.from('1 3 7 234889141 0 3 0')});
 assert.equal(sent.length,1);
 assert.equal(n.hangup(),true,'Hermes can cancel pending toolbar invitation');
 assert.equal(timeouts[0].cancelled,true);
 timeouts[0].fn();
 assert.equal(sent.length,1,'cancelled invitation must never start later');
}finally{n.stop();global.setTimeout=oldTimeout;global.clearTimeout=oldClear;}
""")

    def test_unanswered_button_call_expires_without_blocking_future_calls(self):
        self.run_js(r"""
const assert=require('assert');
const {NativeCall}=require('./native_call.js');
const sent=[],timers=[];
const priorSet=global.setTimeout,priorClear=global.clearTimeout;
global.setTimeout=(fn,ms)=>{const t={fn,ms,cleared:false};timers.push(t);return t;};
global.clearTimeout=t=>{if(t)t.cleared=true;};
const n=new NativeCall({client:{email:'bot@hermes.local',sendNativeSignal:(to,t,p)=>
 sent.push({t,p})},owner:'owner@hermes.local',host:'192.168.1.81',
 xpHost:'192.168.1.84',token:'a'.repeat(64),
 logger:{info(){},warn(){},error(){}}});
try {
 assert.equal(n.invite(),true);
 const expiry=timers.find(t=>t.ms===20000);
 assert(expiry,'unanswered SIP invite must have a short setup timeout');
 expiry.fn();
 assert.equal(n.call,null,'stale outbound invite must release call state');
 assert.equal(n.invite(),true,'a subsequent user or Hermes call can proceed');
 assert.equal(n.hangup(),true);
}finally {
 n.stop();global.setTimeout=priorSet;global.clearTimeout=priorClear;
}
""")

    def test_talk_failure_reconnects_without_hanging_up_messenger(self):
        self.run_js(r"""
const assert=require('assert');
const net=require('net');
const {EventEmitter}=require('events');
const {NativeCall}=require('./native_call.js');
const originalConnect=net.connect,originalTimeout=global.setTimeout;
const originalClear=global.clearTimeout,originalInterval=global.setInterval;
const originalClearInterval=global.clearInterval;
const timers=[],connections=[],sent=[];
global.setTimeout=(fn,delay)=>{const t={fn,delay,cancelled:false};timers.push(t);return t;};
global.clearTimeout=t=>{if(t)t.cancelled=true;};
global.setInterval=(fn,delay)=>({fn,delay});
global.clearInterval=()=>{};
net.connect=()=>{const conn=new EventEmitter();
 conn.destroyed=false;
 conn.writableLength=0;
 conn.write=()=>{};
 conn.destroy=()=>{conn.destroyed=true;conn.emit('close');};
 connections.push(conn);return conn;};
const n=new NativeCall({
 client:{email:'bot@hermes.local',
 sendNativeSignal:(to,type,payload)=>sent.push(type)},
 owner:'owner@hermes.local',host:'192.168.1.81',
 xpHost:'192.168.1.84',token:'a'.repeat(64),
 logger:{info(){},warn(){},error(){}}
});
const call={
 remote:{ip:'192.168.1.84',port:12221},seq:0,stamp:0,ssrc:10,
 id:'call-123',output:Buffer.alloc(0),
};
try{
 n.call=call;
 n.startTalk(call);
 assert.equal(connections.length,1);
 connections[0].emit('connect');
 const ready=Buffer.from([0,0,0,1,82]); // Talk frame: R
 connections[0].emit('data',ready);
 assert.equal(call.talkReady,true);
 call.output=Buffer.alloc(160,0x31);
 connections[0].emit('close');
 assert.equal(n.call,call,'Talk failure must not terminate SIP call');
 assert.equal(call.talkReady,false);
 assert.equal(call.output.length,0,'discard stale provider audio');
 assert.equal(sent.length,0,'never issue a SIP BYE for a Talk interruption');
 assert.equal(call.talk,null);
 const retry=timers.find(t=>t.delay===500);
 assert(retry);
 retry.fn();
 assert.equal(connections.length,2,'reconnect within same WLM SIP call');
 connections[1].emit('data',ready);
 assert.equal(call.talkReady,true);
 assert.equal(call.talkReconnects,0,'clear exponential backoff after recovery');
 assert.equal(n.call,call);
 // End Call cancels the media reconnect and destroys the connection.
 n.hangup();
 assert.equal(n.call,null);
 assert.equal(connections[1].destroyed,true);
 assert.equal(sent.length,1,'explicit hangup still sends SIP BYE');
}finally{
 n.stop();
 net.connect=originalConnect;
 global.setTimeout=originalTimeout;global.clearTimeout=originalClear;
 global.setInterval=originalInterval;global.clearInterval=originalClearInterval;
}
""")

    def test_original_wlm_outgoing_sip_preempts_reciprocal_fallback(self):
        self.run_js(r"""
const assert=require('assert');
const {NativeCall,encodeNativeSignal,decodeNativeSignal}=require('./native_call.js');
const saved=[],sent=[];
const oldSet=global.setTimeout,oldClear=global.clearTimeout;
global.setTimeout=(fn,delay)=>{const entry={fn,delay,cleared:false};saved.push(entry);return entry;};
global.clearTimeout=entry=>{if(entry)entry.cleared=true;};
const n=new NativeCall({
 client:{email:'bot@hermes.local',sendNativeSignal:(to,type,payload)=>
   sent.push({type,payload})},
 owner:'owner@hermes.local',host:'192.168.1.81',xpHost:'192.168.1.84',
 token:'a'.repeat(64),logger:{info(){},warn(){},error(){}}
});
try{
 n.onSignal({sender:'owner@hermes.local',type:11,
   payload:Buffer.from('1 3 7 234889141 0 3 0')});
 const fallback=saved.find(t=>t.delay===2500);
 assert(fallback,'allow 2.5 seconds for original Computer Call SIP');
 const sdp='v=0\r\nc=IN IP4 192.168.1.84\r\nm=audio 33555 RTP/AVP 0\r\n';
 const sip=[
 'INVITE sip:bot@hermes.local SIP/2.0',
 'Via: SIP/2.0/UDP 192.168.1.84:5060',
 'From: <sip:owner@hermes.local>;tag=original',
 'To: <sip:bot@hermes.local>',
 'Call-ID: original-call-1','CSeq: 1 INVITE',
 'Content-Type: application/sdp',
 'Content-Length: '+Buffer.byteLength(sdp),'',sdp,
 ].join('\r\n');
 n.onSignal({sender:'owner@hermes.local',type:12,
   payload:encodeNativeSignal('original-call-1',Buffer.from(sip))});
 assert(fallback.cleared,'WLM original SIP INVITE takes priority');
 assert.equal(n.call.id,'original-call-1');
 assert.equal(n.call.initiated,undefined,'one native outbound call, no Hermes reciprocal call');
 assert(decodeNativeSignal(sent[1].type,sent[1].payload).sip.toString().startsWith('SIP/2.0 200 OK'));
 fallback.fn();
 assert.equal(sent.length,2,'late fallback cannot generate a second SIP INVITE');
 n.closeCall();
}finally{n.stop();global.setTimeout=oldSet;global.clearTimeout=oldClear;}
""")

    def test_pcmu_rtp_conversions(self):
        self.run_js(r"""
const assert = require('assert');
const {
  ulawEncode,ulawDecode,encodeRtp,parseRtp,resamplePcm8To16,pcmuToTalk,talkFrame
} = require('./native_call.js');
for (const value of [-32000,-16000,-2000,-100,0,100,2000,16000,32000]) {
  const encoded=ulawEncode(value);
  const decoded=ulawDecode(encoded);
  assert(Math.abs(value-decoded) < Math.max(350,Math.abs(value)*.13));
}
const payload=Buffer.alloc(160,ulawEncode(4000));
const frame=encodeRtp(payload,12,12345,6789);
assert.deepEqual(parseRtp(frame),payload);
assert.equal(resamplePcm8To16(payload).length,640);
assert.equal(pcmuToTalk(payload).length,960);
assert.equal(talkFrame('I',pcmuToTalk(payload)).length,965);
assert.equal(parseRtp(Buffer.from('bad')),null);
""")

    def test_rtp_streams_directly_to_talk_and_returns_pcmu(self):
        self.run_js(r"""
const assert = require('assert');
const {performance} = require('perf_hooks');
const {NativeCall, ulawEncode, ulawDecode, encodeRtp, parseRtp,
       pcmuToTalk, talkFrame} = require('./native_call.js');
const packets=[];
const native = new NativeCall({
  client:{}, owner:'user@hermes.local', host:'192.168.1.81',
  xpHost:'192.168.1.84', token:'x'.repeat(64),
  logger:{info(){},warn(){},error(){}},
});
native.sock.send = data=>packets.push(data);
const written=[];
const call={remote:{ip:'192.168.1.84',port:24100},
  seq:2,stamp:1024,ssrc:5, talkReady:true,
  talk:{write:buf=>written.push(buf),writableLength:0,destroyed:false,destroy(){}},
  talkIncoming:Buffer.alloc(0),talkRemainder:Buffer.alloc(0),
  output:Buffer.alloc(0),outSpeaking:false,packetAt:performance.now()};
native.call=call;
const incoming=Buffer.alloc(160,ulawEncode(1800));
const rtp=encodeRtp(incoming,1,160,55);
native.onRtp(rtp,{address:'192.168.1.85',port:24100});
native.onRtp(rtp,{address:'192.168.1.84',port:24101});
assert.equal(written.length,0);
native.onRtp(rtp,{address:'192.168.1.84',port:24100});
assert.equal(written.length,1);
assert.equal(written[0].readUInt32BE(0),961);
assert.equal(written[0][4],'I'.charCodeAt(0));
assert.equal(written[0].length,965);
assert.equal(pcmuToTalk(incoming).length,960);
// A 1 second 24kHz signed stream becomes 1 second of 8kHz PCMU.
const spoken=Buffer.alloc(48000);
for(let i=0;i<spoken.length/2;i++) spoken.writeInt16LE(5000,i*2);
const output=talkFrame('O',spoken);
native.onTalkData(call,output.subarray(0,13));
assert.equal(call.output.length,0);
native.onTalkData(call,output.subarray(13));
assert.equal(call.output.length,8000);
call.packetAt=performance.now()-10;
for(let i=0;i<19;i++){
  native.tickTalkAudio(call);
  call.packetAt=performance.now()-10;
}
assert(packets.length>=15);
const media=packets.map(parseRtp);
assert(media.some(payload=>Math.abs(ulawDecode(payload[0]))>1000));
for(let i=1;i<packets.length;i++){
 assert.equal(packets[i].readUInt16BE(2),(packets[i-1].readUInt16BE(2)+1)&0xffff);
 assert.equal(packets[i].readUInt32BE(4),packets[i-1].readUInt32BE(4)+160);
}
native.stop();
""")

    def test_diagnostic_separates_audible_speech_reset_from_empty_turn_clear(self):
        """The Realtime D event is not always an audible interruption."""
        self.run_js(r"""
const assert=require('assert');
const {NativeCall,talkFrame}=require('./native_call.js');
const logged=[];
const native=new NativeCall({
 client:{},owner:'owner@example.invalid',host:'127.0.0.1',
 xpHost:'127.0.0.2',token:'x'.repeat(64),
 logger:{info:(...args)=>logged.push(args),warn(){},error(){}}
});
const call={
 remote:{ip:'127.0.0.2',port:1234},output:Buffer.alloc(0),
 talkIncoming:Buffer.alloc(0),talkRemainder:Buffer.alloc(0),
 outSpeaking:false
};
native.call=call;
native.onTalkData(call,talkFrame('D'));
assert.equal(call.interruptions,1);
assert.equal(call.resetsDuringSpeech||0,0);
assert.equal(call.discardedPcmMs||0,0);
call.output=Buffer.alloc(160*15,0x7f); // 300ms queued speech
call.outSpeaking=true;
native.onTalkData(call,talkFrame('D'));
assert.equal(call.interruptions,2);
assert.equal(call.resetsDuringSpeech,1);
assert.equal(call.discardedPcmMs,300);
assert.equal(call.output.length,0);
native.logCallStats(call);
assert(logged.at(-1)[0].includes('resets_during_speech=%d discarded_pcm=%dms'));
assert.deepEqual(logged.at(-1).slice(-2),[1,300]);
native.stop();
""")

    def test_reorder_dedup_jitter_preroll_and_no_packet_bursts(self):
        self.run_js(r"""
const assert=require('assert');
const {performance}=require('perf_hooks');
const {NativeCall,encodeRtp,ulawEncode,parseRtp}=require('./native_call.js');
const native=new NativeCall({
  client:{},owner:'owner@example.invalid',host:'192.168.1.81',
  xpHost:'192.168.1.84',token:'x'.repeat(64),
  logger:{info(){},warn(){},error(){}},
});
const outbound=[], sent=[];
native.sock.send=packet=>outbound.push(Buffer.from(packet));
const call={remote:{ip:'192.168.1.84',port:24500},seq:5,stamp:1234,ssrc:10,
 talkReady:true,talk:{write:data=>sent.push(data),writableLength:0,destroyed:false,destroy(){}},
 output:Buffer.alloc(0),outSpeaking:false,packetAt:performance.now()};
native.call=call;
for(const n of [10,10,9,11,14]){
 const frame=encodeRtp(Buffer.alloc(160,ulawEncode(3000)),n,n*160,12);
 native.onRtp(frame,{address:'192.168.1.84',port:24500});
}
assert.equal(sent.length,3,'duplicate and reordered microphone RTP must be ignored');
assert.equal(call.incomingLost,2,'sequence gaps must be tracked');
// 100ms is too little to start a stable word: preserve it while sending silence.
call.output=Buffer.alloc(160*5,ulawEncode(9000));
native.tickTalkAudio(call);
assert.equal(parseRtp(outbound.at(-1))[0],0xff);
assert.equal(call.output.length,800);
// Once 800ms is buffered, the speech begins with an RTP marker bit.
call.output=Buffer.alloc(160*45,ulawEncode(9000));
call.lastOutputAt=performance.now();
call.packetAt=performance.now()-10;
native.tickTalkAudio(call);
assert.equal(call.output.length,160*44);
assert(outbound.at(-1)[1]&0x80);
// Brief source underrun should NOT force another 800ms speech prebuffer.
call.output=Buffer.alloc(0);
call.packetAt=performance.now()-10;
native.tickTalkAudio(call);
assert(call.outSpeaking,'small PCM gap must preserve speech mode');
assert.equal(call.outputUnderflows,1);
call.output=Buffer.alloc(160,ulawEncode(9000));
call.lastOutputAt=performance.now();
call.packetAt=performance.now()-10;
native.tickTalkAudio(call);
assert.equal(call.output.length,0,'next 20ms of speech plays immediately');
// If a timer fires 120ms late, do not burst 3 packets at WLM.
const count=outbound.length;
const beforeStamp=call.stamp;
call.packetAt=performance.now()-120;
native.tickTalkAudio(call);
assert.equal(outbound.length,count+1);
assert(call.stamp>beforeStamp+160);
assert(call.timerSlips>=4);
native.stop();
""")

    def test_rtp_sender_uses_monotonic_deadlines_not_polling_timer(self):
        self.run_js(r"""
const assert=require('assert');
const {performance}=require('perf_hooks');
const {NativeCall}=require('./native_call.js');
const native=new NativeCall({
 client:{},owner:'owner@example.invalid',host:'127.0.0.1',
 xpHost:'127.0.0.2',token:'x'.repeat(64),
 logger:{info(){},warn(){},error(){}}
});
native.sock.send=()=>{};
const call={remote:{ip:'127.0.0.2',port:9000},output:Buffer.alloc(160*1000,0xff),
 outSpeaking:true,seq:0,stamp:0,ssrc:2,packetAt:performance.now()+20};
native.call=call;
const oldSetTimeout=global.setTimeout;
const oldClearTimeout=global.clearTimeout;
const timers=[];
global.setTimeout=(cb,delay)=>{timers.push({cb,delay});return timers.length;};
global.clearTimeout=()=>{};
try {
 native.scheduleTalkAudio(call);
 assert.equal(timers.length,1);
 assert(timers[0].delay>10 && timers[0].delay<=21,
  'timer should target the next 20ms packet deadline');
 call.packetAt=performance.now()-1;
 timers[0].cb();
 assert.equal(timers.length,2);
 assert(timers[1].delay>10 && timers[1].delay<=21,
  'after a packet, schedule directly to its following deadline');
 assert.equal(call.seq,1,'exactly one packet must be emitted');
 native.closeCall();
 timers[1].cb();
 assert.equal(timers.length,2,'closed calls must not schedule more packets');
} finally {
 global.setTimeout=oldSetTimeout;
 global.clearTimeout=oldClearTimeout;
 native.stop();
}
""")

    def test_configurable_40ms_rtp_preserves_speech_tails_and_timestamps(self):
        self.run_js(r"""
const assert=require('assert');
const {performance}=require('perf_hooks');
const {NativeCall,ulawEncode,parseRtp}=require('./native_call.js');
const packets=[];
const native=new NativeCall({
 client:{}, owner:'owner@example.invalid', host:'127.0.0.1',
 xpHost:'127.0.0.2',token:'x'.repeat(64),packetMs:40,
 logger:{info(){},warn(){},error(){}}
});
native.sock.send=frame=>packets.push(Buffer.from(frame));
const call={remote:{ip:'127.0.0.2',port:9000},seq:0,stamp:1000,ssrc:5,
 packetAt:performance.now()-1,output:Buffer.alloc(320*21,ulawEncode(9000)),
 outSpeaking:false,lastOutputAt:performance.now()};
native.call=call;
native.tickTalkAudio(call);
assert.equal(packets.length,1);
assert.equal(packets[0].length,332,'40ms PCMU is 320 bytes + RTP header');
assert.equal(packets[0].readUInt32BE(4),1000);
assert.equal(call.stamp,1320);
assert(packets[0][1]&0x80,'first voiced packet should carry RTP marker');
assert.equal(call.outPlayedMs,40);
assert.equal(call.output.length,320*20);
call.output=Buffer.alloc(160,ulawEncode(9000));
call.packetAt=performance.now()-1;
native.tickTalkAudio(call);
assert.equal(packets.length,2);
assert.equal(parseRtp(packets[1]).length,320);
assert.equal(parseRtp(packets[1])[0],ulawEncode(9000));
assert.equal(parseRtp(packets[1])[159],ulawEncode(9000));
assert.equal(parseRtp(packets[1])[160],0xff,'last 20ms padded with silence');
assert.equal(call.outPlayedMs,60,'count only actual voice audio');
assert.equal(call.output.length,0);
assert.equal(call.stamp,1640);
// Very short responses still play after the existing stale-response delay.
call.outSpeaking=false;
call.output=Buffer.alloc(160,ulawEncode(9000));
call.lastOutputAt=performance.now()-300;
call.packetAt=performance.now()-1;
native.tickTalkAudio(call);
assert.equal(call.output.length,0);
assert.equal(call.outPlayedMs,80);
assert(packets[2][1]&0x80,'short reply starts its own marked talkspurt');
assert.throws(()=>new NativeCall({
 client:{},owner:'owner@example.invalid',host:'127.0.0.1',
 xpHost:'127.0.0.2',token:'x'.repeat(64),packetMs:60,
 logger:{info(){},warn(){},error(){}}
}),/20 or 40/);
native.stop();
""")


if __name__ == '__main__':
    unittest.main()
