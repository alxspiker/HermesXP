// drive107.cs - click the Install button (id 107) in the HermesXP window.
using System;
using System.Runtime.InteropServices;
class D107 {
    [DllImport("user32.dll")] static extern IntPtr FindWindow(string c, string t);
    [DllImport("user32.dll")] static extern IntPtr GetDlgItem(IntPtr h, int id);
    [DllImport("user32.dll")] static extern int SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    static void Main() {
        IntPtr w = FindWindow("HermesXPMainWindow", null);
        Console.WriteLine("window=" + w.ToString());
        if (w == IntPtr.Zero) return;
        SetForegroundWindow(w);
        IntPtr btn = GetDlgItem(w, 107);
        Console.WriteLine("install-btn=" + btn.ToString());
        if (btn == IntPtr.Zero) return;
        SendMessage(btn, 245, IntPtr.Zero, IntPtr.Zero);
        Console.WriteLine("install-clicked");
    }
}
