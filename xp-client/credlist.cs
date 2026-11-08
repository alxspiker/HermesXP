using System;
using System.Runtime.InteropServices;

class CredList {
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CredEnumerate(string filter, int flags, out int count, out IntPtr creds);
    [DllImport("advapi32.dll")]
    static extern void CredFree(IntPtr cred);
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct CREDENTIAL {
        public int Flags; public int Type;
        public string TargetName; public string Comment;
        public long LastWritten; public int CredentialBlobSize;
        public IntPtr CredentialBlob; public int Persist;
        public int AttributeCount; public IntPtr Attributes;
        public string TargetAlias; public string UserName;
    }

    static void Main(string[] args) {
        int count; IntPtr creds;
        if (!CredEnumerate(null, 0, out count, out creds)) {
            Console.WriteLine("CredEnumerate failed, err={0}", Marshal.GetLastWin32Error());
            return;
        }
        Console.WriteLine("count={0}", count);
        for (int i = 0; i < count; i++) {
            IntPtr p = Marshal.ReadIntPtr(creds, i * IntPtr.Size);
            CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(p, typeof(CREDENTIAL));
            Console.WriteLine("target=[{0}] user=[{1}] type={2} persist={3}",
                c.TargetName, c.UserName, c.Type, c.Persist);
        }
        CredFree(creds);
    }
}
