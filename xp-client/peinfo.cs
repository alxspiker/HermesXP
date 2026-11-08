// peinfo.cs - print PE header values needed by the import patcher. Usage: peinfo.exe <path>
using System;
using System.IO;
class Q {
    static ushort U16(byte[] b, int o){ return (ushort)(b[o] | (b[o+1] << 8)); }
    static uint U32(byte[] b, int o){ return (uint)(b[o] | (b[o+1] << 8) | (b[o+2] << 16) | (b[o+3] << 24)); }
    static void Main(string[] args){
        byte[] b = File.ReadAllBytes(args[0]);
        uint peOff = U32(b, 0x3C);
        int nsec = U16(b, (int)peOff+6);
        int optSize = U16(b, (int)peOff+20);
        int optOff = (int)peOff+24;
        uint sizeHeaders = U32(b, optOff+60);
        uint sizeImage = U32(b, optOff+56);
        uint secAlign = U32(b, optOff+32);
        uint fileAlign = U32(b, optOff+36);
        uint impRVA = U32(b, optOff+96+8);
        int secOff = optOff+optSize;
        Console.WriteLine("nsec=" + nsec + " optSize=" + optSize + " sizeHeaders=0x" + sizeHeaders.ToString("X") + " sizeImage=0x" + sizeImage.ToString("X"));
        Console.WriteLine("secAlign=0x" + secAlign.ToString("X") + " fileAlign=0x" + fileAlign.ToString("X") + " impRVA=0x" + impRVA.ToString("X"));
        Console.WriteLine("secHeadersEnd=0x" + (secOff+nsec*40).ToString("X") + " needForNew=0x" + (secOff+(nsec+1)*40).ToString("X") + " slack=" + (sizeHeaders - (secOff+(nsec+1)*40)));
        for(int i=0;i<nsec;i++){
            int o = secOff+i*40;
            string nm = "";
            for(int k=0;k<8 && b[o+k]!=0;k++) nm += (char)b[o+k];
            Console.WriteLine("sec " + nm + " va=0x" + U32(b,o+12).ToString("X") + " vs=0x" + U32(b,o+8).ToString("X") + " raw=0x" + U32(b,o+20).ToString("X") + " rawsz=0x" + U32(b,o+16).ToString("X"));
        }
    }
}
