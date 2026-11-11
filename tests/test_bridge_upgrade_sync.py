"""Prevent plugin upgrades from omitting locally required Messenger modules."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "local-server/update-xp.sh"
LIVE_ENTRYPOINT = ROOT / "msn-bridge/bridge.js"
CLIENT_ENTRYPOINT = ROOT / "msn-bridge/msnclient/main.js"


class BridgeUpgradeSyncTests(unittest.TestCase):
    def test_update_copies_all_local_bridge_modules(self):
        script = SCRIPT.read_text()
        required = (
            "bridge.js", "native_call.js", "lan_address.js",
            "file_transfer.js", "offline_queue.js", "wlm_presence.js",
            "msnclient/frame.js", "msnclient/sso.js", "msnclient/main.js",
        )
        for module in required:
            with self.subTest(module=module):
                self.assertTrue((ROOT / "msn-bridge" / module).is_file())
                self.assertIn(module, script)
        self.assertIn('for file in "${BRIDGE_FILES[@]}"; do', script)
        self.assertIn('if [ ! -s "$REPO/msn-bridge/$file" ]; then', script)
        self.assertIn('mv -f "$dest.tmp" "$dest"', script)
        self.assertNotIn("node_modules", script.split("BRIDGE_FILES=(", 1)[1].split(")", 1)[0])

    def test_entrypoints_require_modules_in_reviewed_repository(self):
        bridge_source = LIVE_ENTRYPOINT.read_text()
        client_source = CLIENT_ENTRYPOINT.read_text()
        self.assertIn("require('./file_transfer.js')", bridge_source)
        self.assertIn("require('./offline_queue.js')", bridge_source)
        self.assertIn("require('../wlm_presence.js')", client_source)
        self.assertIn("require('../file_transfer.js')", client_source)


if __name__ == "__main__":
    unittest.main()
