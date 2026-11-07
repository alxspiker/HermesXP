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

if __name__=='__main__':unittest.main()
