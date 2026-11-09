'use strict';
// Local Escargot MSN server's legacy Passport RST2 SSO authentication.
// Server issues an RPS challenge and validates HMAC-SHA1 + 3DES-CBC from
// the BinarySecret returned by RST2.srf. All calls stay on 127.0.0.1.
const crypto = require('crypto');

function rpsKey(key, message) {
  const hash = (bytes) => crypto.createHmac('sha1', key).update(bytes).digest();
  const hash1 = hash(message);
  const hash2 = hash(Buffer.concat([hash1, message]));
  const hash3 = hash(hash1);
  const hash4 = hash(Buffer.concat([hash3, message]));
  return Buffer.concat([hash2, hash4.subarray(0,4)]);
}
function signChallenge(secret, challenge) {
  const key = Buffer.from(secret,'base64');
  const proof = Buffer.from(challenge, 'utf8');
  if (key.length !== 24 || !/^[A-Za-z0-9+/=]{64}$/.test(challenge))
    throw new Error('Invalid RPS challenge or proof key');
  const hashKey = rpsKey(key, Buffer.from('WS-SecureConversationSESSION KEY HASH'));
  const cipherKey = rpsKey(key, Buffer.from('WS-SecureConversationSESSION KEY ENCRYPTION'));
  const iv = crypto.randomBytes(8);
  const mac = crypto.createHmac('sha1',hashKey).update(proof).digest();
  const c = crypto.createCipheriv('des-ede3-cbc',cipherKey,iv);
  const encrypted = Buffer.concat([c.update(proof),c.final()]);
  const header=Buffer.alloc(28);
  [28,1,0x6603,0x8004,8,20,encrypted.length].forEach((n,i)=>header.writeUInt32LE(n,i*4));
  return Buffer.concat([header,iv,mac,encrypted]).toString('base64');
}
async function loginSSO(url, email, password, challenge) {
  const axios = require('axios');
  if (!/^http:\/\/127\.0\.0\.1:8081\/RST2\.srf$/.test(url))
    throw new Error('SSO login URL must be the pinned local MSN server');
  const encode = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;')
                         .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const body = [
    '<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">',
    '<Header><Security><Username>' + encode(email) + '</Username>',
    '<Password>' + encode(password) + '</Password></Security></Header>',
    '<Body><RequestMultipleSecurityTokens><RequestSecurityToken>',
    '<Address>messengerclear.live.com</Address>',
    '</RequestSecurityToken></RequestMultipleSecurityTokens></Body></Envelope>',
  ].join('');
  const response = await axios.post(url, body, {
    headers:{'Content-Type':'text/xml; charset=utf-8'},timeout:10000,
    maxContentLength:400000,
  });
  const xml = String(response.data);
  // RST2 template returns one compact token (with fixed random suffix) and
  // a BinarySecret when the request contains messengerclear.live.com.
  // The RST2 response begins with a *static Passport.NET/tb* proof token;
  // that is NOT the 24-byte proof key for our MSN login. Scope both token
  // and BinarySecret to the Compact1 response (messengerclear.live.com).
  const start = xml.indexOf('<wsse:BinarySecurityToken Id="Compact1">');
  const end = xml.indexOf('</wst:RequestSecurityTokenResponse>', start);
  if (start < 0 || end < start) throw new Error('SSO Compact1 section missing');
  const section = xml.slice(start, end);
  const token = section.match(/<wsse:BinarySecurityToken[^>]*>t=([A-Za-z0-9]{20})/);
  const secret = section.match(/<wst:BinarySecret>([A-Za-z0-9+/=]{32})<\/wst:BinarySecret>/);
  if (!token || !secret) throw new Error('SSO server did not return RPS proof material');
  return {token:token[1], proof:signChallenge(secret[1], challenge)};
}
module.exports={rpsKey,signChallenge,loginSSO};
