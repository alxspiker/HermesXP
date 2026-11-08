using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

class Signin2 {
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

        /* Clear email field, paste email. */
        SendKeys.SendWait("^a");
        Thread.Sleep(200);
        SendKeys.SendWait("{DEL}");
        Thread.Sleep(200);
        Clipboard.SetText(email);
        SendKeys.SendWait("^v");
        Thread.Sleep(400);

        /* Tab to password, clear it, type password slowly. */
        SendKeys.SendWait("{TAB}");
        Thread.Sleep(400);
        SendKeys.SendWait("^a");
        Thread.Sleep(200);
        SendKeys.SendWait("{DEL}");
        Thread.Sleep(200);
        foreach (char c in pw) {
            SendKeys.SendWait(c.ToString());
            Thread.Sleep(120);
        }
        Thread.Sleep(500);

        /* Verify password length via clipboard (length only). */
        SendKeys.SendWait("^a");
        Thread.Sleep(300);
        SendKeys.SendWait("^c");
        Thread.Sleep(300);
        string t = "";
        try { t = Clipboard.GetText(); } catch { t = "<err>"; }
        int len = t.Length;
        Console.WriteLine("pw_len={0} expected={1}", len, pw.Length);
        try { Clipboard.SetText(""); } catch { }
        if (len != pw.Length) {
            Console.WriteLine("ABORT: password length mismatch, not submitting");
            return;
        }
        /* Re-type is not needed: the ^a/^c left the text selected, so just
           press Enter to submit (selected text stays). */
        SendKeys.SendWait("{ENTER}");
        Console.WriteLine("submitted");
    }
}
