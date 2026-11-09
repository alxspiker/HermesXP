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

    def test_headless_wifi_scan_does_not_include_credentials(self):
        source=(HERE/'xp-client'/'hermesxp.c').read_text()
        self.assertIn('str_find(cl,"/wifi-scan")',source)
        self.assertIn('write_wifi_scan_report()',source)
        # Scanning reports SSIDs only, never key material.
        a=source.index('static void write_wifi_scan_report(void)')
        z=source.index('static int same_ssid(',a)
        self.assertNotIn('g_wifi_password',source[a:z])
        self.assertNotIn('g_ownerPw',source[a:z])

if __name__=='__main__':unittest.main()
