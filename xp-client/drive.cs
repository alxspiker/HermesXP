// drive.cs - diagnostic: find HermesXP, set the caller-specified server IP, click Test (id 103).
using System;
using System.Runtime.InteropServices;
using System.Text;
class D {
    [DllImport("user32.dll")] static extern IntPtr FindWindow(string c, string t);
    [DllImport("user32.dll")] static extern IntPtr GetDlgItem(IntPtr h, int id);
    [DllImport("user32.dll")] static extern int SendMessage(IntPtr h, uint m, IntPtr w, string l);
    [DllImport("user32.dll")] static extern int SendMessage(IntPtr h, uint m, IntPtr w, StringBuilder l);
    [DllImport("user32.dll")] static extern int SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    static void Main(string[] args) {
        System.Net.IPAddress parsedIp;
        if (args.Length != 1 || !System.Net.IPAddress.TryParse(args[0], out parsedIp)) {
            Console.Error.WriteLine("Usage: drive.exe <server-ip>");
            return;
        }
        IntPtr w = FindWindow("HermesXPMainWindow", null);
        Console.WriteLine("window=" + w.ToString());
        if (w == IntPtr.Zero) return;
        SetForegroundWindow(w);
        IntPtr edit = GetDlgItem(w, 102);
        IntPtr btn = GetDlgItem(w, 103);
        Console.WriteLine("edit=" + edit.ToString() + " btn=" + btn.ToString());
        SendMessage(edit, 12, IntPtr.Zero, args[0]);
        StringBuilder sb = new StringBuilder(100);
        SendMessage(edit, 13, (IntPtr)100, sb);
        Console.WriteLine("edit-now=" + sb.ToString());
        SendMessage(btn, 245, IntPtr.Zero, IntPtr.Zero);
        Console.WriteLine("clicked");
    }
}
