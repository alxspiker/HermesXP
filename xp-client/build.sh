#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for lib in kernel32 user32 ws2_32 crypt32 shell32 advapi32 iphlpapi gdi32; do lld-link /lib /def:"$lib.def" /machine:x86 /out:"$lib.lib"; done
python3 fix_import_names.py kernel32.lib user32.lib ws2_32.lib crypt32.lib shell32.lib advapi32.lib iphlpapi.lib gdi32.lib
# The old __chkstk stub was an invalid no-op. On x86 Windows, __chkstk
# is responsible for BOTH probing and allocating frames larger than 4 KiB.
# Returning without changing ESP corrupted the window callback's stack.
# This small no-CRT client disables automatic probes and commits 64 KiB
# up-front (well above its largest frame), removing the need for the stub.
clang -target i686-pc-windows-msvc -O2 -fno-stack-protector -mno-stack-arg-probe -ffreestanding -fms-extensions -c hermesxp.c -o hermesxp.obj
if llvm-nm -u hermesxp.obj | grep -q '__chkstk'; then
  echo '[build] ERROR: stack allocation still depends on __chkstk' >&2
  exit 1
fi
lld-link /safeseh:no /machine:x86 /subsystem:windows,5.01 /stack:1048576,65536 /entry:WinMainCRTStartup /nodefaultlib /brepro /out:HermesXP.exe hermesxp.obj kernel32.lib user32.lib ws2_32.lib crypt32.lib shell32.lib advapi32.lib iphlpapi.lib gdi32.lib
clang -target i686-pc-windows-msvc -O2 -fno-stack-protector -mno-stack-arg-probe -ffreestanding -c hermesxp-updater.c -o hermesxp-updater.obj
lld-link /safeseh:no /machine:x86 /subsystem:windows,5.01 /stack:1048576,65536 /entry:WinMainCRTStartup /nodefaultlib /brepro /out:HermesXP-Updater.exe hermesxp-updater.obj kernel32.lib ws2_32.lib
clang -target i686-pc-windows-msvc -O2 -fno-stack-protector -mno-stack-arg-probe -ffreestanding -c hermesxp-service.c -o hermesxp-service.obj
lld-link /safeseh:no /machine:x86 /subsystem:windows,5.01 /stack:1048576,65536 /entry:WinMainCRTStartup /nodefaultlib /brepro /out:HermesXP-Service.exe hermesxp-service.obj kernel32.lib advapi32.lib ws2_32.lib
llvm-objdump -p HermesXP.exe | grep -E 'Machine|Subsystem|DLL Name' || true
