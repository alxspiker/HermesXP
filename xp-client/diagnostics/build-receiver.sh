#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
lld-link /lib /def:kernel32.def /machine:x86 /out:rtp-diag-kernel32.lib
lld-link /lib /def:ws2_32.def /machine:x86 /out:rtp-diag-ws2_32.lib
python3 ../fix_import_names.py rtp-diag-kernel32.lib rtp-diag-ws2_32.lib
clang -target i686-pc-windows-msvc -O2 -fno-stack-protector \
  -mno-stack-arg-probe -ffreestanding -c rtp-receiver.c -o rtp-receiver.obj
lld-link /safeseh:no /machine:x86 /subsystem:console,5.01 \
  /stack:1048576,65536 /entry:mainCRTStartup /nodefaultlib /brepro \
  /out:RtpReceiverDiag.exe rtp-receiver.obj rtp-diag-kernel32.lib rtp-diag-ws2_32.lib
llvm-objdump -p RtpReceiverDiag.exe | grep -E 'Machine|Subsystem|DLL Name'
