import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class BridgeRecoveryTest(unittest.TestCase):
    def test_msn_disconnect_exits_nonzero_for_supervisor_restart(self):
        harness = r'''
const EventEmitter = require('events');
const Module = require('module');
const original = Module._load;
class FakeClient extends EventEmitter {
  execute() { setTimeout(() => this.emit('close'), 25); }
}
Module._load = function(request, ...args) {
  if (request === './msnclient/main.js') return {MSNClient: FakeClient};
  return original.call(this, request, ...args);
};
require(process.argv[1]);
'''
        env = dict(os.environ, MSN_BOT_EMAIL='test@example.invalid', MSN_BOT_PASSWORD='test', HERMES_MSN_BRIDGE_TOKEN='x'*32)
        try:
            result = subprocess.run(['node', '-e', harness, str(ROOT / 'msn-bridge' / 'bridge.js')], env=env, capture_output=True, text=True, timeout=3)
        except subprocess.TimeoutExpired:
            self.fail('bridge stayed alive after MSN disconnected')
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_standalone_sender_requires_token_and_owner_and_is_loopback_only(self):
        harness = r'''
const EventEmitter = require('events');
const Module = require('module');
const http = require('http');
const original = Module._load;
let sent = [];
class FakeClient extends EventEmitter {
  constructor(){ super(); this.active = true; }
  execute(){ this.emit('msg',{type:'connected'}); }
  async sendMessage(to,text){sent.push({to,text});}
}
Module._load = function(request,...args){
  if(request === './msnclient/main.js') return {MSNClient: FakeClient};
  return original.call(this,request,...args);
};
require(process.argv[1]);
function req(to,text,token){
  return new Promise((resolve,reject)=>{
    let bytes=Buffer.from(JSON.stringify({to,text}));
    let request=http.request({
      host:'127.0.0.1',port:18769,path:'/send',method:'POST',
      headers:{'X-Hermes-Token':token,'Content-Length':bytes.length}
    },response=>{
      let body='';response.on('data',b=>body+=b);
      response.on('end',()=>resolve({code:response.statusCode,body}));
    });
    request.on('error',reject);request.end(bytes);
  });
}
setTimeout(async ()=>{
  try{
    const invalid=await req('owner@example.invalid','wrong token','bad');
    const forbidden=await req('stranger@example.invalid','bad recipient','z'.repeat(32));
    const permitted=await req('owner@example.invalid','test','z'.repeat(32));
    const result=invalid.code===401 && forbidden.code===403 &&
                 permitted.code===202 && sent.length===1 &&
                 sent[0].to==='owner@example.invalid' && sent[0].text==='test';
    console.log(result?'STANDALONE_MSN_AUTH_TEST_PASS':'STANDALONE_MSN_AUTH_TEST_FAIL');
    process.exit(result?0:8);
  }catch(err){console.error(err);process.exit(9);}
},120);
'''
        env = dict(os.environ, MSN_BOT_EMAIL='bot@example.invalid', MSN_BOT_PASSWORD='test',
                   HERMES_MSN_OWNER_EMAIL='owner@example.invalid',
                   HERMES_MSN_BRIDGE_TOKEN='z'*32)
        result = subprocess.run(['node', '-e', harness, str(ROOT / 'msn-bridge' / 'bridge.js')],
                                env=env, capture_output=True, text=True, timeout=4)
        self.assertEqual(result.returncode, 0, result.stdout[-350:]+result.stderr[-350:])
        self.assertIn('STANDALONE_MSN_AUTH_TEST_PASS', result.stdout)

if __name__ == '__main__':
    unittest.main()
