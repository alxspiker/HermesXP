using System;
using System.Text;
using System.Runtime.InteropServices;

class EnumChild {
    [DllImport("user32.dll")]
    static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")]
    static extern bool EnumChildWindows(IntPtr hWndParent, EnumChildProc lpEnumFunc, IntPtr lParam);
    delegate bool EnumChildProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int nMaxCount);
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int nMaxCount);
    [DllImport("user32.dll")]
    static extern int GetDlgCtrlID(IntPtr hWnd);
    [DllImport("user32.dll")]
    static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    [StructLayout(LayoutKind.Sequential)]
    struct RECT { public int Left, Top, Right, Bottom; }

    static bool CB(IntPtr hWnd, IntPtr lParam) {
        StringBuilder cls = new StringBuilder(256);
        StringBuilder txt = new StringBuilder(256);
        GetClassName(hWnd, cls, 256);
        GetWindowText(hWnd, txt, 256);
        RECT r; GetWindowRect(hWnd, out r);
        Console.WriteLine("child hwnd={0} id={1} class={2} text=[{3}] rect=({4},{5})-({6},{7})",
            hWnd.ToInt64(), GetDlgCtrlID(hWnd), cls, txt, r.Left, r.Top, r.Right, r.Bottom);
        return true;
    }

    static void Main(string[] args) {
        string cls = args.Length > 0 ? args[0] : "MSBLWindowClass";
        IntPtr w = FindWindow(cls, null);
        Console.WriteLine("window={0}", w.ToInt64());
        if (w == IntPtr.Zero) return;
        EnumChildWindows(w, CB, IntPtr.Zero);
    }
}
