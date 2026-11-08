using System;
using System.Runtime.InteropServices;
using System.Text;

class ClickBtn {
    [DllImport("user32.dll")]
    static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int nMaxCount);
    [DllImport("user32.dll")]
    static extern IntPtr GetDlgItem(IntPtr hDlg, int nIDDlgItem);
    [DllImport("user32.dll")]
    static extern IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    const uint BM_CLICK = 0xF5;
    static string needle;
    static int btnId;

    static bool CB(IntPtr hWnd, IntPtr lParam) {
        StringBuilder sb = new StringBuilder(256);
        GetWindowText(hWnd, sb, 256);
        string t = sb.ToString();
        if (t.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0) {
            IntPtr btn = GetDlgItem(hWnd, btnId);
            Console.WriteLine("dialog=[{0}] btn={1}", t, btn.ToInt64());
            if (btn != IntPtr.Zero) SendMessage(btn, BM_CLICK, IntPtr.Zero, IntPtr.Zero);
            return false;
        }
        return true;
    }

    static void Main(string[] args) {
        needle = args[0];
        btnId = int.Parse(args[1]);
        EnumWindows(CB, IntPtr.Zero);
        Console.WriteLine("done");
    }
}
