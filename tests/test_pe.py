"""Binary header validation, independent of Wine/Windows XP runtime."""
from pathlib import Path
import struct
import unittest

HERE=Path(__file__).resolve().parents[1]

class TestPE(unittest.TestCase):
    def test_service_is_native_xp_32bit_without_desktop_privileges(self):
        b = (HERE/'dist'/'HermesXP-Service.exe').read_bytes()
        self.assertEqual(b[:2], b'MZ')
        offset = struct.unpack_from('<I', b, 0x3c)[0]
        self.assertEqual(b[offset:offset+4], b'PE\0\0')
        self.assertEqual(struct.unpack_from('<H', b, offset+4)[0], 0x14c)
        opt = offset+24
        self.assertEqual(struct.unpack_from('<H', b, opt+48)[0], 5)
        self.assertEqual(struct.unpack_from('<H', b, opt+50)[0], 1)
        self.assertIn(b'KERNEL32.dll', b)
        self.assertIn(b'ADVAPI32.dll', b)
        self.assertIn(b'WS2_32.dll', b)
        source = (HERE/'xp-client/hermesxp-service.c').read_text()
        self.assertIn('NT AUTHORITY\\\\LocalService', source)
        self.assertNotIn('SERVICE_INTERACTIVE_PROCESS', source)
        self.assertNotIn('CreateProcessAsUser', source)
        self.assertNotIn('CreateProcessA(', source)

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
        self.assertIn(b'CONNECTION',exe)
        self.assertIn(b'Settings...',exe)
        self.assertIn(b'Repair Messenger',exe)
        self.assertIn(b'Runs automatically at Windows sign-in.',exe)
        self.assertNotIn(b'First connection',exe)
        self.assertNotIn(b'Install for MSN',exe)
        self.assertNotIn(b'Screenshot saved',exe)
        self.assertNotIn(b'Scan Wi-Fi',exe)
        self.assertNotIn(b'Connect Wi-Fi',exe)

    def test_compact_interface_uses_real_embedded_logo(self):
        from PIL import Image
        source = (HERE/'xp-client/hermesxp.c').read_text()
        build = (HERE/'xp-client/build.sh').read_text()
        resources = (HERE/'xp-client/hermesxp.rc').read_text()
        image = HERE/'assets/hermesxp-logo.jpg'
        self.assertTrue(image.exists(), 'The supplied logo must ship as an actual image')
        with Image.open(image) as logo:
            self.assertGreaterEqual(logo.width, 250)
        self.assertIn('1 ICON "hermesxp.ico"', resources)
        self.assertIn('2 BITMAP "hermesxp-banner.bmp"', resources)
        self.assertIn('llvm-rc /FO hermesxp.res hermesxp.rc', build)
        self.assertIn('hermesxp.obj hermesxp.res', build)
        self.assertIn('LoadImageA(g_instance,(const char*)2,IMAGE_BITMAP', source)
        self.assertIn('toggle_settings(HWND h)', source)
        self.assertIn('if(msg==WM_COMMAND && (w&0xFFFF)==117)', source)
        self.assertIn('for(int i=0;i<6;i++)ShowWindow(g_advanced[i],0)', source)
        self.assertNotIn('add("BUTTON","Screenshot"', source)
        self.assertNotIn('g_heading_font', source)

    def test_update_cache_includes_gui_resources(self):
        import importlib.util
        path=HERE/'tools/update_manager.py'
        import ast
        module=ast.parse(path.read_text())
        digest_fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='source_digest')
        text=ast.get_source_segment(path.read_text(),digest_fn)
        for ext in ('*.rc','*.ico','*.bmp'):
            self.assertIn(ext,text, f'{ext} should invalidate the update cache')

if __name__=='__main__':unittest.main()
