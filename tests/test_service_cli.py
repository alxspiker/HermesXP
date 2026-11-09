import unittest
from unittest.mock import patch

from tools.hermesxp_services import main, select_device


class ServiceCliTests(unittest.TestCase):
    def setUp(self):
        self.devices = [
            {"name": "XP-Lab", "host": "192.168.1.84", "token": "a" * 64, "port": 18768},
            {"name": "XP-Office", "host": "192.168.1.85", "token": "b" * 64, "port": 18768},
        ]

    def test_only_paired_device_can_be_selected(self):
        self.assertEqual(select_device(self.devices, "xp-lab")["host"], "192.168.1.84")
        self.assertEqual(select_device(self.devices, "192.168.1.85")["name"], "XP-Office")
        with self.assertRaises(ValueError):
            select_device(self.devices, None)
        with self.assertRaises(ValueError):
            select_device(self.devices, "XP-Unpaired")

    def test_request_for_general_service_uses_existing_pairing(self):
        with patch("tools.hermesxp_services.read_registry", return_value=self.devices), \
             patch("tools.hermesxp_services.HermesXPClient") as client:
            client.return_value.service.return_value = "service=Spooler state=running win32_error=0"
            self.assertEqual(main([
                "--device", "XP-Office", "--service", "Spooler", "start"
            ]), 0)
            client.assert_called_once_with("192.168.1.85", "b" * 64, port=18768, timeout=9)
            client.return_value.service.assert_called_once_with("Spooler", "start")


if __name__ == "__main__":
    unittest.main()
