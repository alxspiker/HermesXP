"""ABI guard for the small XP-SP3 WLAN declarations used by the freestanding client."""
import pathlib
import unittest

HEADER = pathlib.Path(__file__).resolve().parents[1] / "xp-client" / "wlan_api.h"


class WlanAbiTests(unittest.TestCase):
    def test_wlan_header_declares_xp_api_entry_points_and_layout_guards(self):
        source = HEADER.read_text(encoding="utf-8")
        for required in (
            "WlanOpenHandle", "WlanEnumInterfaces", "WlanScan",
            "WlanGetAvailableNetworkList", "WlanSetProfile", "WlanConnect",
            "WlanQueryInterface", "WlanFreeMemory", "WlanCloseHandle",
            "WLAN_INTERFACE_INFO", "WLAN_AVAILABLE_NETWORK",
            "WLAN_CONNECTION_PARAMETERS", "XP SP3",
        ):
            with self.subTest(declaration=required):
                self.assertIn(required, source)

    def test_wlan_header_uses_xp_profile_only_connection_mode(self):
        source = HEADER.read_text(encoding="utf-8")
        self.assertIn("wlan_connection_mode_profile", source)
        self.assertNotIn("wlan_connection_mode_temporary_profile = 3", source)

    def test_companion_exposes_wifi_scan_picker(self):
        source = (HEADER.parent / "hermesxp.c").read_text(encoding="utf-8")
        self.assertIn('"Scan Wi-Fi"', source)
        self.assertIn("WlanGetAvailableNetworkList", source)
        self.assertIn("CB_ADDSTRING", source)

    def test_companion_has_profile_connect_and_password_controls(self):
        source = (HEADER.parent / "hermesxp.c").read_text(encoding="utf-8")
        profile = (HEADER.parent / "wifi_profile.h").read_text(encoding="utf-8")
        self.assertIn('"Connect Wi-Fi"', source)
        self.assertIn('"EDIT"', source)
        self.assertIn("WlanSetProfile", source)
        self.assertIn("WlanConnect", source)
        self.assertIn("hermesxp_build_wifi_profile", source)
        self.assertIn("auth_id == 4", profile)
        self.assertIn("auth_id == 7", profile)
        self.assertIn("wifi_xml_escaped", profile)
        self.assertIn("wipe_xml", source)
        self.assertIn("XP WLAN profiles may not encrypt it at rest", source)


if __name__ == "__main__":
    unittest.main()
