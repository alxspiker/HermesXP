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
""")

    def test_sip_sdp_offer_accept_and_reject(self):
        self.run_js(r"""
const assert = require('assert');
const {parseSip, parseSdp, sipResponse, NativeCall} = require('./native_call.js');
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
const sent = [];
const native = new NativeCall({
  client:{sendNativeSignal:(to,type,data)=>sent.push({to,type,data})},
  owner:'user@hermes.local',host:'127.0.0.1',xpHost:'192.168.1.84',
  token:'x'.repeat(64),logger:{info:()=>{}, warn:()=>{}, error:()=>{}},
});
native.onSignal({sender:'evil@hermes.local',type:1,payload:message});
assert.equal(sent.length,0);
native.onSignal({sender:'user@hermes.local',type:1,payload:message});
assert.equal(sent.length,1);
assert.equal(native.call.remote.port,30000);
assert(sent[0].data.toString().startsWith('SIP/2.0 200'));
native.onSignal({sender:'user@hermes.local',type:1,payload:message});
assert(sent[1].data.toString().startsWith('SIP/2.0 486'));
native.stop();
""")

    def test_pcmu_rtp_conversions(self):
        self.run_js(r"""
const assert = require('assert');
const {
  ulawEncode,ulawDecode,encodeRtp,parseRtp,resamplePcm8To16
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
assert.equal(parseRtp(Buffer.from('bad')),null);
""")


if __name__ == '__main__':
    unittest.main()
