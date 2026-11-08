using System;
using System.Diagnostics;
class L {
  static void Main() {
    Process p = new Process();
    p.StartInfo.FileName = "C:\\HermesXP.exe";
    p.StartInfo.UseShellExecute = false;
    try { p.Start(); } catch (Exception e) { Console.WriteLine("START FAILED: " + e.Message); return; }
    bool exited = p.WaitForExit(3000);
    Console.WriteLine("exited=" + exited + " code=" + (exited ? p.ExitCode.ToString() : "?") + " title=" + p.MainWindowTitle);
    if (!exited) { Console.WriteLine("still running, handle=" + p.MainWindowHandle); p.Kill(); }
  }
}
