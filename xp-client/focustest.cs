using System;
using System.Threading;
using System.Windows.Forms;
using System.Runtime.InteropServices;

class FocusTest {
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

    [STAThread]
    static void Main(string[] args) {
        string email = args[0];
        IntPtr w = IntPtr.Zero;
        for (int i = 0; i < 30; i++) {
            w = FindWindow("MSBLWindowClass", null);
            if (w != IntPtr.Zero) break;
            Thread.Sleep(500);
        }
        Console.WriteLine("window={0}", w.ToInt64());
        if (w == IntPtr.Zero) return;
        uint pid;
        uint wlmTid = GetWindowThreadProcessId(w, out pid);
        AttachThreadInput(GetCurrentThreadId(), wlmTid, true);
        SetForegroundWindow(w);
        Thread.Sleep(1500);
        /* Paste email into the focused field, then select-all + copy to see
           what actually landed there. */
        Clipboard.SetText(email);
        SendKeys.SendWait("^v");
        Thread.Sleep(500);
        SendKeys.SendWait("^a");
        Thread.Sleep(300);
        SendKeys.SendWait("^c");
        Thread.Sleep(500);
        string got = "";
        try { got = Clipboard.GetText(); } catch { got = "<clipboard read failed>"; }
        Console.WriteLine("field contains: [{0}]", got);
        Console.WriteLine("expected:       [{0}]", email);
        Console.WriteLine("match={0}", got == email);
    }
}
