# MSN file-transfer fixture coverage

`msn-bridge/file_transfer.js` mediates in-band MSNP/P2P transfers for the configured owner only. It rejects legacy address-based invites and never dials invite-supplied hosts or ports. File bytes remain in a private host-side transfer directory; chat events carry metadata and hashes, not contents.

The host fixture `tests/file_transfer_cases.js` exercises invitation, acceptance, chunk ordering, completion, peer cancellation/BYE acknowledgement, rejection/failure, filename and executable filtering, symlink/path escapes, per-file and active-transfer limits, and content non-disclosure. Inbox/outbox directories are created with restricted permissions; files are bounded to 8 MiB by default. Configured lower limits apply to inbound and outbound transfers.

This is protocol-fixture evidence only. It does not verify real Windows XP/Windows Live Messenger behavior; no physical XP machine is touched by these tests.
