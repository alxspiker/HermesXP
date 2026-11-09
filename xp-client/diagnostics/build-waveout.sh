#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
lld-link /lib /def:kernel32.def /machine:x86 /out:audio-diag-kernel32.lib
lld-link /lib /def:winmm.def /machine:x86 /out:audio-diag-winmm.lib
python3 ../fix_import_names.py audio-diag-kernel32.lib audio-diag-winmm.lib
clang -target i686-pc-windows-msvc -O2 -fno-stack-protector \
  -mno-stack-arg-probe -ffreestanding -c waveout-timing.c -o waveout-timing.obj
lld-link /safeseh:no /machine:x86 /subsystem:console,5.01 \
  /stack:1048576,65536 /entry:mainCRTStartup /nodefaultlib /brepro \
  /out:WaveOutTiming.exe waveout-timing.obj audio-diag-kernel32.lib audio-diag-winmm.lib
llvm-objdump -p WaveOutTiming.exe | grep -E 'Machine|Subsystem|DLL Name'
