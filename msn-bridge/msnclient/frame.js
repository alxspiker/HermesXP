'use strict';
// MSNP notification-server byte framing. UBN / UUN bodies can be binary;
// splitting socket chunks on CRLF loses or corrupts SIP and P2P payloads.
const WITH_PAYLOAD = new Set([
  'UUX', 'MSG', 'QRY', 'NOT', 'GCF', 'ADL', 'FQY', 'RML',
  'UUN', 'UUM', 'PUT', 'DEL', 'SDG', 'VAS', 'SDC', 'UBN',
]);

class MSNPFrameDecoder {
  constructor(maxFrame = 65536) {
    this.pending = Buffer.alloc(0);
    this.maxFrame = maxFrame;
  }

  feed(bytes) {
    const part = Buffer.isBuffer(bytes) ? bytes : Buffer.from(bytes);
    if (part.length + this.pending.length > this.maxFrame * 2)
      throw new Error('MSNP input exceeds bounded buffer');
    this.pending = Buffer.concat([this.pending, part]);
    const frames = [];
    for (;;) {
      const end = this.pending.indexOf('\r\n');
      if (end < 0) break;
      if (end > 2048) throw new Error('MSNP command line too long');
      const line = this.pending.subarray(0, end).toString('utf8');
      const words = line.split(' ');
      let count = 0;
      // Server UUN acknowledgement has no body: "UUN <trid> OK".
      if (WITH_PAYLOAD.has(words[0]) &&
          !(words[0] === 'UUN' && words[words.length - 1] === 'OK')) {
        const value = words[words.length - 1];
        if (!/^(0|[1-9][0-9]{0,5})$/.test(value))
          throw new Error('Invalid MSNP payload length');
        count = Number(value);
        if (count > this.maxFrame)
          throw new Error('MSNP payload exceeds size limit');
      }
      if (this.pending.length < end + 2 + count) break;
      const body = this.pending.subarray(end + 2, end + 2 + count);
      frames.push({command: words[0], words, body: Buffer.from(body)});
      this.pending = this.pending.subarray(end + 2 + count);
    }
    if (this.pending.length > this.maxFrame + 2048)
      throw new Error('MSNP incomplete frame exceeds size limit');
    return frames;
  }
}
module.exports = {MSNPFrameDecoder};
