using System;
using System.Runtime.InteropServices;
class CredDelete {
    [DllImport("advapi32.dll", EntryPoint="CredDelete", SetLastError=true, CharSet=CharSet.Unicode)]
    static extern bool CredDeleteNative(string target, int type, int flags);
    [STAThread]
    static void Main(string[] args) {
        // Delete all credentials whose target contains the given substring.
        // Lists first via CredEnumerate would be nicer; here we delete the
        // known WindowsLive targets for the given account explicitly.
        string acct = args[0];
        string[] targets = {
            "WindowsLive:name=" + acct,
            "WindowsLive:(token):name=" + acct + ";serviceuri=contacts.msn.com",
            "WindowsLive:(token):name=" + acct + ";serviceuri=sup.live.com",
            "WindowsLive:(token):name=" + acct + ";serviceuri=messengersecure.live.com",
            "WindowsLive:(token):name=" + acct + ";serviceuri=messengerclear.live.com",
            "WindowsLive:(token):name=" + acct + ";serviceuri=messenger.msn.com",
            "WindowsLive:(token):name=" + acct + ";serviceuri=storage.msn.com",
        };
        foreach (string t in targets) {
            bool ok = CredDeleteNative(t, 1, 0);
            Console.WriteLine((ok ? "deleted " : "notfound ") + t);
        }
    }
}
