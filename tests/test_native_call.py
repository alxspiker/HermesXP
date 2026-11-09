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
// A 0.5 second 24kHz signed stream becomes 0.5 seconds of 8kHz PCMU.
const spoken=Buffer.alloc(24000);
for(let i=0;i<spoken.length/2;i++) spoken.writeInt16LE(5000,i*2);
const output=talkFrame('O',spoken);
native.onTalkData(call,output.subarray(0,13));
assert.equal(call.output.length,0);
native.onTalkData(call,output.subarray(13));
assert.equal(call.output.length,4000);
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
// Once 400ms is buffered, the speech begins with an RTP marker bit.
call.output=Buffer.alloc(160*25,ulawEncode(9000));
call.lastOutputAt=performance.now();
call.packetAt=performance.now()-10;
native.tickTalkAudio(call);
assert.equal(call.output.length,160*24);
assert(outbound.at(-1)[1]&0x80);
// Brief source underrun should NOT force another 400ms speech prebuffer.
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


if __name__ == '__main__':
    unittest.main()
