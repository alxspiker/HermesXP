#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for lib in kernel32 user32 ws2_32 crypt32 shell32; do lld-link /lib /def:"$lib.def" /machine:x86 /out:"$lib.lib"; done
python3 fix_import_names.py kernel32.lib user32.lib ws2_32.lib crypt32.lib shell32.lib
clang -target i686-pc-windows-msvc -O2 -fno-stack-protector -ffreestanding -fms-extensions -c hermesxp.c -o hermesxp.obj
lld-link /machine:x86 /subsystem:windows,5.01 /entry:WinMainCRTStartup /nodefaultlib /brepro /out:HermesXP.exe hermesxp.obj kernel32.lib user32.lib ws2_32.lib crypt32.lib shell32.lib
llvm-objdump -p HermesXP.exe | grep -E 'Machine|Subsystem|DLL Name' || true
