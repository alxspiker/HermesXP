"""Fix LLVM lld-generated stdcall import lib to use undecorated Windows DLL names.
COFF short import header NameType=3 (UNDECORATE), not 2 (NOPREFIX).
This preserves __imp__Function@N symbols while importing Function from XP DLL.
"""
from pathlib import Path
import struct
import sys
for name in sys.argv[1:]:
    p=Path(name)
    b=bytearray(p.read_bytes())
    if b[:8]!=b'!<arch>\n':raise ValueError(f'Unexpected archive format: {p}')
    o=8; modified=0
    while o+60<=len(b):
        size=int(bytes(b[o+48:o+58]))
        s=o+60
        if b[s:s+4]==b'\x00\x00\xff\xff':
            type_info=struct.unpack_from('<H',b,s+18)[0]
            if (type_info>>2)&0x7 == 2:
                # NameType is bits 2..4, type in bits 0..1.
                type_info = (type_info & ~0x1c) | (3<<2)
                struct.pack_into('<H',b,s+18,type_info)
                modified+=1
        o=s+size+(size&1)
    if not modified: raise ValueError(f'No short import members found in {p}')
    p.write_bytes(b)
    print(f'{p}: patched {modified} stdcall imports to undecorated DLL entry names')
