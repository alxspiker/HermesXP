# Windows XP waveOut playback timing diagnostic

Build from Linux with bash xp-client/diagnostics/build-waveout.sh. The
result is a freestanding 32-bit XP SP3 console application that uses
standard WinMM (waveOutOpen, 8 kHz mono PCM16), and plays 12 seconds
of digital silence through the default playback device.

Run WaveOutTiming.exe for eight buffers (160 ms), WaveOutTiming.exe /4
for four buffers (80 ms), or WaveOutTiming.exe /2 for two buffers
(40 ms). It reports how many 20 ms buffers complete during 12 seconds
and timing variation in per-buffer completion intervals. It neither
records microphone/speaker audio nor invokes Messenger APIs.

The test is a capacity demonstration of XP's WinMM playback path,
not an inspection of Windows Live Messenger's proprietary audio queue.
FreeSSHd console sessions may deliver the output as wrapped lines.
The application creates no registry keys or permanent configuration.

Observed on RUITER, MSI Wind U100, Windows XP SP3, November 9, 2026:

| Playback queue | Frames completed / approx 600 | Largest same-buffer interval |
|---|---:|---:|
| 160 ms (8 buffers) | 598 | 173 ms |
| 80 ms (4 buffers) | 598 | 94 ms |
| 40 ms (2 buffers) | 431 (twice) | 64–78 ms |

These numbers support investigating shallow playout-buffer sensitivity,
but cannot prove that WLM uses waveOut or that sending longer RTP frames
increases its actual playback queue. Retest independently per machine.
