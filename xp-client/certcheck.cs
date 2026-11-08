// certcheck.cs - list Trusted Root certs (Local Machine, then Current User).
using System;
using System.Security.Cryptography.X509Certificates;
class C {
    static void Main() {
        foreach (StoreLocation loc in new StoreLocation[] { StoreLocation.LocalMachine, StoreLocation.CurrentUser }) {
            Console.WriteLine("STORE " + loc.ToString());
            try {
                X509Store s = new X509Store(StoreName.Root, loc);
                s.Open(OpenFlags.ReadOnly);
                foreach (X509Certificate2 c in s.Certificates) Console.WriteLine("  " + c.Subject);
                s.Close();
            } catch (Exception e) { Console.WriteLine("  ERROR " + e.Message); }
        }
    }
}
