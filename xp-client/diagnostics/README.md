# XP RTP receiver arrival check

Temporary, read-only Windows XP SP3 diagnostic for native MSN calling.
Build on the Debian Hermes host with:

    bash xp-client/diagnostics/build-receiver.sh

This creates a 32-bit Windows 5.01 console executable, not a replacement
HermesXP client. Run it on XP with the host's sender address as an argument:

```text
rtp-receiver.exe 192.168.1.20
```

The address above is only an example. It binds a regular UDP socket on the active XP interface,
port 45678, for
25 seconds; no raw-IP capture or administrator privileges are required.

The diagnostic measures only timing and RTP header metadata for a test
stream of SILENT PCMU packets from the specified Hermes host to the XP device.
It does not inspect, save, transmit or print microphone or speaker samples.

It exits after 25 seconds and prints the received packet count, missing RTP
sequence numbers, duplicate packets, packet spacing below 15 ms, above 25 ms,
above 40 ms, and minimum/maximum arrival intervals in whole milliseconds.
Use with a known 20-ms-spaced RTP stream from the Debian host, and compare
to the host sender timing. This tests the XP UDP networking path, not the
Windows Live Messenger application's receiving jitter buffer or sound card.
An earlier raw-capture variant could fail on XP (Winsock 10022).

Do not leave this running unattended or expose the XP laptop to external
networks. Remove the temporary executable from XP after testing.
