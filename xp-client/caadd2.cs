using System;
using System.IO;
using System.Security.Cryptography.X509Certificates;

class CaAdd {
    static void Main(string[] args) {
        string path = args[0];
        string where = args.Length > 1 ? args[1] : "LocalMachine";
        byte[] raw = File.ReadAllBytes(path);
        X509Certificate2 cert = new X509Certificate2(raw);
        Console.WriteLine("subject={0}", cert.Subject);
        Console.WriteLine("issuer={0}", cert.Issuer);
        StoreLocation loc = where == "CurrentUser" ? StoreLocation.CurrentUser : StoreLocation.LocalMachine;
        X509Store store = new X509Store(StoreName.Root, loc);
        store.Open(OpenFlags.ReadWrite);
        store.Add(cert);
        store.Close();
        Console.WriteLine("added to {0} Root", loc);
        /* Verify it is really there. */
        X509Store verify = new X509Store(StoreName.Root, loc);
        verify.Open(OpenFlags.ReadOnly);
        bool found = false;
        foreach (X509Certificate2 c in verify.Certificates) {
            if (c.Thumbprint == cert.Thumbprint) { found = true; break; }
        }
        verify.Close();
        Console.WriteLine("verified present: {0}", found);
    }
}
