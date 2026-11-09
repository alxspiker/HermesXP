# RUITER RTP receiver arrival check

Temporary, read-only Windows XP SP3 diagnostic for native MSN calling.
Build on the Debian Hermes host with:

    bash xp-client/diagnostics/build-receiver.sh

This creates a 32-bit Windows 5.01 console executable, not a replacement
HermesXP client. It binds a Winsock IPv4 raw socket on 192.168.1.84 and
enables SIO_RCVALL (requires local administrator privileges).

The diagnostic captures only timing and RTP header metadata for PCMU
packets from Hermes 192.168.1.81 to RUITER 192.168.1.84. It does not
inspect, save, transmit or print microphone or speaker samples.

It exits after 25 seconds and prints the received packet count, missing RTP
sequence numbers, duplicate packets, packet spacing below 15 ms, above 25 ms,
above 40 ms, and minimum/maximum arrival intervals in whole milliseconds.
Use with a known 20-ms-spaced RTP stream from the Debian host, and compare
to HermesXP's sender pacing logs. The OS may reject raw sockets or
SIO_RCVALL; in that case the tool prints a stage and Winsock error code.

Do not leave this running unattended or expose the XP laptop to external
networks. Remove the temporary executable from RUITER after testing.
