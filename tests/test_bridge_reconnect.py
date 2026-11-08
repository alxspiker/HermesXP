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

if __name__ == '__main__':
    unittest.main()
