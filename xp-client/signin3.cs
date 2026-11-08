using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

class Signin3 {
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
        string email = args[0];
        string pw = args[1];
        IntPtr h = FindWindow("MSBLWindowClass", null);
        if (h == IntPtr.Zero) { Console.WriteLine("window=0"); return; }
        uint pid; uint tid = GetWindowThreadProcessId(h, out pid);
        uint me = GetCurrentThreadId();
        AttachThreadInput(me, tid, true);
        SetForegroundWindow(h);
        AttachThreadInput(me, tid, false);
        Thread.Sleep(800);
        // Clear email field: End, then Shift+Home to select all, then Del.
        SendKeys.SendWait("{END}");
        Thread.Sleep(150);
        SendKeys.SendWait("+{HOME}");
        Thread.Sleep(150);
        SendKeys.SendWait("{DEL}");
        Thread.Sleep(200);
        Clipboard.SetText(email);
        SendKeys.SendWait("^v");
        Thread.Sleep(400);
        // Tab to password, clear with End + Shift+Home + Del, then Backspaces.
        SendKeys.SendWait("{TAB}");
        Thread.Sleep(400);
        SendKeys.SendWait("{END}");
        Thread.Sleep(150);
        SendKeys.SendWait("+{HOME}");
        Thread.Sleep(150);
        SendKeys.SendWait("{DEL}");
        Thread.Sleep(200);
        for (int i = 0; i < 20; i++) { SendKeys.SendWait("{BS}"); Thread.Sleep(40); }
        Thread.Sleep(200);
        foreach (char c in pw) { SendKeys.SendWait(c.ToString()); Thread.Sleep(120); }
        Thread.Sleep(500);
        SendKeys.SendWait("{END}");
        Thread.Sleep(150);
        SendKeys.SendWait("+{HOME}");
        Thread.Sleep(150);
        SendKeys.SendWait("^c");
        Thread.Sleep(300);
        string t = "";
        try { t = Clipboard.GetText(); } catch { t = "<err>"; }
        Console.WriteLine("pw_len={0} expected={1}", t.Length, pw.Length);
        try { Clipboard.SetText(""); } catch { }
        if (t.Length != pw.Length) { Console.WriteLine("ABORT"); return; }
        SendKeys.SendWait("{ENTER}");
        Console.WriteLine("submitted");
    }
}
