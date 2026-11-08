"""Apply HermesXP deployment patches to the cloned msn-server tree.

The server code is downloaded at install time (not vendored), so fixes for
its drift against modern dependencies live here and are applied by
install.sh right after the pinned checkout. Each patch is small, guarded
(only applied when the exact upstream text is present), and documented
below. Re-running is safe: already-patched text is left alone.

Patches:
  1. HLL 3.0 stats restore (core/stats.py::_stats_from_json): upstream calls
     hll.set_registers(...), which HLL >= 3.0 removed (its HyperLogLog has
     registers() but no setter). On the first restart after stats were
     persisted, Stats.__init__ crashed with
     AttributeError: 'HLL.HyperLogLog' object has no attribute
     'set_registers', crash-looping the server. The fix keeps the restore
     when the method exists and starts the active-user counter fresh
     otherwise — that counter is a vanity stat for a two-user server.

Usage: python patch-server.py <server-dir>
"""
import sys

PATCHES = [
    (
        "core/stats.py",
        "\t\thll = HyperLogLog(12)\n\t\thll.set_registers(bytearray(json['users_active']))\n\t\tstats['users_active'] = hll\n",
        "\t\thll = HyperLogLog(12)\n\t\t# HLL >= 3.0 removed set_registers; start the counter fresh.\n\t\tif hasattr(hll, 'set_registers'):\n\t\t\thll.set_registers(bytearray(json['users_active']))\n\t\tstats['users_active'] = hll\n",
    ),
]


def main():
    server_dir = sys.argv[1]
    for relpath, old, new in PATCHES:
        path = f"{server_dir}/{relpath}"
        text = open(path).read()
        if new in text:
            print(f"{relpath}: already patched")
            continue
        if old not in text:
            print(f"{relpath}: upstream text not found, NOT patched", file=sys.stderr)
            sys.exit(1)
        open(path, "w").write(text.replace(old, new, 1))
        print(f"{relpath}: patched")


if __name__ == "__main__":
    main()
