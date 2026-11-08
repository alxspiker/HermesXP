using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

class ReadEmail {
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
        /* Select all in the focused field, copy, read clipboard. Assumes
           focus is on the email field (it is at sign-in window open). */
        SendKeys.SendWait("^a");
        Thread.Sleep(300);
        SendKeys.SendWait("^c");
        Thread.Sleep(300);
        string t = "";
        try { t = Clipboard.GetText(); } catch { t = "<clipboard error>"; }
        Console.WriteLine("email=[{0}]", t);
    }
}
