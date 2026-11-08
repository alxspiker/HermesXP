// pecheck.cs - list the DLLs in a PE32 exe's import table. Usage: pecheck.exe <path>
using System;
using System.IO;
class P {
    static ushort U16(byte[] b, int o){ return (ushort)(b[o] | (b[o+1] << 8)); }
    static uint U32(byte[] b, int o){ return (uint)(b[o] | (b[o+1] << 8) | (b[o+2] << 16) | (b[o+3] << 24)); }
    static uint RvaToOff(byte[] b, uint rva, int secOff, int nsec, uint sizeHeaders){
        if(rva < sizeHeaders) return rva;
        for(int i=0;i<nsec;i++){
            uint va = U32(b, secOff+i*40+12);
            uint vs = U32(b, secOff+i*40+8); if(vs==0) vs = U32(b, secOff+i*40+16);
            uint raw = U32(b, secOff+i*40+20);
            if(rva >= va && rva < va+vs) return raw + (rva-va);
        }
        return 0xFFFFFFFF;
    }
    static void Main(string[] args){
        byte[] b = File.ReadAllBytes(args[0]);
        if(b[0]!='M' || b[1]!='Z'){ Console.WriteLine("not MZ"); return; }
        uint peOff = U32(b, 0x3C);
        int nsec = U16(b, (int)peOff+6);
        int optSize = U16(b, (int)peOff+20);
        int optOff = (int)peOff+24;
        uint sizeHeaders = U32(b, optOff+60);
        int secOff = optOff+optSize;
        uint impRVA = U32(b, optOff+96+8);
        uint impOff = RvaToOff(b, impRVA, secOff, nsec, sizeHeaders);
        Console.WriteLine("sections=" + nsec + " importRVA=0x" + impRVA.ToString("X"));
        for(int d=0; d<512; d++){
            uint off = impOff + (uint)d*20;
            if(U32(b,(int)off)==0 && U32(b,(int)off+4)==0 && U32(b,(int)off+8)==0 && U32(b,(int)off+12)==0 && U32(b,(int)off+16)==0) break;
            uint nameRVA = U32(b, (int)off+12);
            uint nameOff = RvaToOff(b, nameRVA, secOff, nsec, sizeHeaders);
            int e = (int)nameOff; string s = "";
            while(e < b.Length && b[e] != 0){ s += (char)b[e]; e++; }
            Console.WriteLine("import: " + s);
        }
    }
}
