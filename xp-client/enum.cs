using System;
using System.Runtime.InteropServices;
using System.Text;
class E {
  delegate bool P(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(P p, IntPtr l);
  [DllImport("user32.dll")] static extern int GetWindowTextA(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern int GetClassNameA(IntPtr h, StringBuilder s, int n);
  static bool Cb(IntPtr h, IntPtr l) {
    StringBuilder t = new StringBuilder(256);
    StringBuilder c = new StringBuilder(256);
    GetWindowTextA(h, t, 256);
    GetClassNameA(h, c, 256);
    if (t.Length > 0) Console.WriteLine(c.ToString() + " - " + t.ToString());
    return true;
  }
  static void Main() { EnumWindows(Cb, IntPtr.Zero); }
}
