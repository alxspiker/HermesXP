using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

class CheckPw {
    [DllImport("user32.dll")]
    static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("user32.dll")]
    static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("kernel32.dll")]
    static extern uint GetCurrentThreadId();

    [STAThread]
    static void Main(string[] args) {
        IntPtr h = FindWindow("MSBLWindowClass", null);
        if (h == IntPtr.Zero) { Console.WriteLine("window=0"); return; }
        uint pid; uint tid = GetWindowThreadProcessId(h, out pid);
        uint me = GetCurrentThreadId();
        AttachThreadInput(me, tid, true);
        SetForegroundWindow(h);
        AttachThreadInput(me, tid, false);
        Thread.Sleep(500);
        /* Tab from email to password field, select all, copy, report LENGTH
           only (never print the password). */
        SendKeys.SendWait("{TAB}");
        Thread.Sleep(500);
        SendKeys.SendWait("^a");
        Thread.Sleep(300);
        SendKeys.SendWait("^c");
        Thread.Sleep(300);
        string t = "";
        try { t = Clipboard.GetText(); } catch { t = "<err>"; }
        Console.WriteLine("pw_len={0}", t.Length);
        /* Clear clipboard so the password does not linger. */
        try { Clipboard.SetText(""); } catch { }
    }
}
