"""Binary header validation, independent of Wine/Windows XP runtime."""
from pathlib import Path
import struct
import unittest

HERE=Path(__file__).resolve().parents[1]

class TestPE(unittest.TestCase):
    def test_xp_x86_gui(self):
        b=(HERE/'dist'/'HermesXP.exe').read_bytes()
        self.assertEqual(b[:2],b'MZ')
        offset=struct.unpack_from('<I',b,0x3c)[0]
        self.assertEqual(b[offset:offset+4],b'PE\0\0')
        self.assertEqual(struct.unpack_from('<H',b,offset+4)[0],0x14c)
        opt=offset+24
        self.assertEqual(struct.unpack_from('<H',b,opt)[0],0x10b)
        self.assertEqual(struct.unpack_from('<H',b,opt+48)[0],5)
        self.assertEqual(struct.unpack_from('<H',b,opt+50)[0],1)
        self.assertEqual(struct.unpack_from('<H',b,opt+68)[0],2)
        self.assertIn(b'KERNEL32.dll',b)
        self.assertIn(b'USER32.dll',b)
        self.assertIn(b'WS2_32.dll',b)
        # The former dummy __chkstk routine was a no-op: Windows x86
        # functions larger than 4 KiB never allocated their stack frame.
        self.assertGreaterEqual(struct.unpack_from('<I',b,opt+76)[0],65536)

    def test_build_never_uses_broken_stack_probe_stub(self):
        build=(HERE/'xp-client'/'build.sh').read_text()
        self.assertIn('-mno-stack-arg-probe',build)
        self.assertIn('/stack:1048576,65536',build)
        self.assertNotIn('chkstk.obj',build)
        self.assertFalse((HERE/'xp-client'/'chkstk.s').exists())

    def test_native_network_status_uses_windows_without_wifi_management(self):
        source=(HERE/'xp-client'/'hermesxp.c').read_text()
        self.assertIn('static void refresh_network_status(void)',source)
        self.assertIn('GetAdaptersInfo(NULL,&size)',source)
        self.assertIn('"Network Connections..."',source)
        self.assertIn('"Refresh status"',source)
        self.assertIn('ShellExecuteA(owner,"open","control.exe","ncpa.cpl"',source)
        self.assertIn('SetTimer(h,1,15000,NULL)',source)
        self.assertIn('KillTimer(h,1)',source)
        self.assertNotIn('wlanapi.dll',source)
        self.assertNotIn('WlanSetProfile',source)
        self.assertNotIn('WlanScan',source)
        self.assertNotIn('"Scan Wi-Fi"',source)
        self.assertNotIn('"Connect Wi-Fi"',source)
        self.assertNotIn('"Wi-Fi passphrase',source)
        self.assertNotIn('/wifi-scan',source)
        for obsolete in ('wlan_api.h','wifi_profile.h'):
            self.assertFalse((HERE/'xp-client'/obsolete).exists())

    def test_network_ui_labels_are_bundled_in_xp_exe(self):
        exe=(HERE/'dist'/'HermesXP.exe').read_bytes()
        self.assertIn(b'Network Connections...',exe)
        self.assertIn(b'Refresh status',exe)
        self.assertIn(b'Network status:',exe)
        self.assertNotIn(b'Scan Wi-Fi',exe)
        self.assertNotIn(b'Connect Wi-Fi',exe)

if __name__=='__main__':unittest.main()
