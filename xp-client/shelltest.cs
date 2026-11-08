// shelltest.cs - launch an exe via ShellExecute and report the return value.
// Usage: shelltest.exe <path>
using System;
using System.Runtime.InteropServices;
class S {
    [DllImport("shell32.dll")] static extern IntPtr ShellExecute(IntPtr h, string op, string f, string p, string d, int s);
    static void Main(string[] args){
        IntPtr r = ShellExecute(IntPtr.Zero, "open", args[0], null, null, 1);
        Console.WriteLine("ShellExecute returned " + r.ToInt64());
    }
}
