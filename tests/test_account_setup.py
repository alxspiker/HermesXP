import importlib.util
import pathlib
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / 'local-server/create-accounts.py'
spec = importlib.util.spec_from_file_location('accounts', path)
accounts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accounts)

class AccountSetupTests(unittest.TestCase):
    def test_bridge_token_is_created_and_reused(self):
        token = accounts.bridge_token({})
        self.assertGreaterEqual(len(token), 64)
        self.assertEqual(accounts.bridge_token({'HERMES_MSN_BRIDGE_TOKEN': token}), token)
        self.assertNotEqual(accounts.bridge_token({}), token)
