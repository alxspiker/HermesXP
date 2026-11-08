using System;
using System.Threading;
using System.Windows.Forms;
using System.Runtime.InteropServices;

class AutoLogin {
    [DllImport("user32.dll")]
    static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("kernel32.dll")]
    static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")]
    static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("user32.dll")]
    static extern IntPtr GetForegroundWindow();

    [STAThread]
    static void Main(string[] args) {
        string email = args[0];
        string pw = args[1];
        IntPtr w = IntPtr.Zero;
        for (int i = 0; i < 30; i++) {
            w = FindWindow("MSBLWindowClass", null);
            if (w != IntPtr.Zero) break;
            Thread.Sleep(500);
        }
        Console.WriteLine("window={0}", w.ToInt64());
        if (w == IntPtr.Zero) return;
        /* Attach our input thread to WLM's so SetForegroundWindow works from
           a console process (otherwise the keystrokes go to the wrong window). */
        uint pid;
        uint wlmTid = GetWindowThreadProcessId(w, out pid);
        uint myTid = GetCurrentThreadId();
        AttachThreadInput(myTid, wlmTid, true);
        bool fg = SetForegroundWindow(w);
        Console.WriteLine("foreground={0} active={1}", fg, GetForegroundWindow() == w);
        Thread.Sleep(1500);
        /* Paste the address (verified to work), Tab to the password field,
           then TYPE the password key by key — Ctrl+V does not land in the
           DirectUI password edit, so paste is unreliable there. */
        Clipboard.SetText(email);
        SendKeys.SendWait("^v");
        Thread.Sleep(300);
        SendKeys.SendWait("{TAB}");
        Thread.Sleep(300);
        foreach (char c in pw) SendKeys.SendWait(c.ToString());
        Thread.Sleep(300);
        SendKeys.SendWait("{TAB}");
        Thread.Sleep(300);
        SendKeys.SendWait(" ");
        Thread.Sleep(300);
        SendKeys.SendWait("{TAB}");
        Thread.Sleep(300);
        SendKeys.SendWait(" ");
        Thread.Sleep(300);
        /* Tab once more to land on the Sign in button, then Space to press it
           (Enter from a checkbox does not reliably submit a DirectUI form). */
        SendKeys.SendWait("{TAB}");
        Thread.Sleep(300);
        SendKeys.SendWait(" ");
        Console.WriteLine("keys sent");
    }
}
