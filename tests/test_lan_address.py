import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestLanAddress(unittest.TestCase):
    def test_automatically_chooses_active_lan_interface_and_rejects_stale_ip(self):
        script = r"""
const assert=require('assert');
const {interfaceForXP}=require('./msn-bridge/lan_address.js');
const interfaces={
  wlo1:[{family:'IPv4',address:'192.168.1.81',netmask:'255.255.255.0',internal:false}],
  tailscale0:[{family:'IPv4',address:'100.97.137.100',netmask:'255.255.255.255',internal:false}],
  lo:[{family:'IPv4',address:'127.0.0.1',netmask:'255.0.0.0',internal:true}]
};
assert.equal(interfaceForXP('192.168.1.78','192.168.1.44',interfaces),'192.168.1.81');
assert.equal(interfaceForXP('192.168.1.78','192.168.1.81',interfaces),'192.168.1.81');
assert.equal(interfaceForXP('192.168.3.44','192.168.1.81',interfaces),null);
const moved={enp1s0:[{family:'IPv4',address:'192.168.3.8',netmask:'255.255.255.0',internal:false}]};
assert.equal(interfaceForXP('192.168.3.44','192.168.1.81',moved),'192.168.3.8');
console.log('Native Messenger LAN interface selection passed');
"""
        result = subprocess.run(["node", "-e", script], cwd=ROOT,
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
