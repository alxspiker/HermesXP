'use strict';

// Determine the actual usable interface each time an XP device or host
// changes IP. Never pin RTP to an environment value whose address is no
// longer assigned. The private LAN interface must be on XP's subnet;
// a Tailscale address or loopback IP isn't a native Messenger media path.
const net = require('net');
const os = require('os');

function to32(ip) {
  if (net.isIP(ip) !== 4) return null;
  return ip.split('.').reduce((acc, octet) => (acc * 256 + Number(octet)) >>> 0, 0);
}

function interfaceForXP(peer, preferred = '', interfaces = os.networkInterfaces()) {
  const peerValue = to32(peer);
  if (peerValue == null) return null;
  let compatible = [];
  for (const [name, addresses] of Object.entries(interfaces)) {
    for (const entry of addresses || []) {
      if (entry.internal || entry.family !== 'IPv4') continue;
      const ipValue = to32(entry.address);
      const maskValue = to32(entry.netmask);
      if (ipValue == null || maskValue == null) continue;
      if (((ipValue & maskValue) >>> 0) === ((peerValue & maskValue) >>> 0)) {
        compatible.push({name, address: entry.address});
      }
    }
  }
  if (!compatible.length) return null;
  // Preserve an explicit setting only while it is a valid assigned
  // interface on the same subnet; otherwise select the viable LAN IP.
  return (compatible.find(item => item.address === preferred) ||
          compatible.find(item => !/tailscale|tun|vpn|docker/i.test(item.name)) ||
          compatible[0]).address;
}

module.exports = {interfaceForXP};
