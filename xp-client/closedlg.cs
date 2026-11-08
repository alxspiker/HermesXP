using System;
using System.Runtime.InteropServices;
using System.Text;

class CloseDlg {
    [DllImport("user32.dll")]
    static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")]
    static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int nMaxCount);
    [DllImport("user32.dll")]
    static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    const uint WM_CLOSE = 0x10;
    static string needle;

    static bool CB(IntPtr hWnd, IntPtr lParam) {
        StringBuilder sb = new StringBuilder(256);
        GetWindowText(hWnd, sb, 256);
        string t = sb.ToString();
        if (t.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0) {
            Console.WriteLine("closing: [{0}] hwnd={1}", t, hWnd.ToInt64());
            PostMessage(hWnd, WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
            return false;
        }
        return true;
    }

    static void Main(string[] args) {
        needle = args[0];
        EnumWindows(CB, IntPtr.Zero);
        Console.WriteLine("done");
    }
}
