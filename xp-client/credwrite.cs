using System;
using System.Runtime.InteropServices;
using System.Text;

class CredWriteTool {
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CredWrite(ref CREDENTIAL cred, int flags);
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
        string email = args[0];
        string pw = args[1];
        byte[] blob = Encoding.Unicode.GetBytes(pw);
        IntPtr blobPtr = Marshal.AllocHGlobal(blob.Length);
        Marshal.Copy(blob, 0, blobPtr, blob.Length);
        CREDENTIAL c = new CREDENTIAL();
        c.Flags = 0;
        c.Type = 1; /* GENERIC */
        c.TargetName = "WindowsLive:name=" + email;
        c.Comment = null;
        c.LastWritten = 0;
        c.CredentialBlobSize = blob.Length;
        c.CredentialBlob = blobPtr;
        c.Persist = 2; /* LOCAL_MACHINE */
        c.AttributeCount = 0;
        c.Attributes = IntPtr.Zero;
        c.TargetAlias = null;
        c.UserName = email;
        bool ok = CredWrite(ref c, 0);
        Console.WriteLine("CredWrite ok={0} err={1}", ok, Marshal.GetLastWin32Error());
        Marshal.FreeHGlobal(blobPtr);
    }
}
