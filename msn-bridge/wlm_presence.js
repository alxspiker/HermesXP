'use strict';
// Presence helpers for the Hermes MSN bot. No network. The scene and
// MSNObject values are produced by local-server/wlm_content.py.
const fs = require('fs');

function chgLine(trid, status, caps, msnobjQuoted) {
  const head = String(trid) + status + String(caps);
  if (/[\s<>]/.test(head)) throw new Error('bad CHG field');
  let line = 'CHG ' + trid + ' ' + status + ' ' + caps;
  if (msnobjQuoted) {
    if (/[\s<>\r\n]/.test(msnobjQuoted)) {
      throw new Error('msnobj must be URL-encoded');
    }
    line += ' ' + msnobjQuoted;
  }
  return line + '\r\n';
}

function xmlEscape(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function uuxCommand(trid, machineGuid, sceneXml) {
  const body = '<Data><MachineGuid>' + xmlEscape(machineGuid) +
    '</MachineGuid><Scene>' + xmlEscape(sceneXml || '') +
    '</Scene><ColorScheme>0</ColorScheme></Data>';
  return 'UUX ' + trid + ' ' + Buffer.byteLength(body, 'utf8') + '\r\n' + body;
}

function decodeScene(value) {
  if (!value) return '';
  if (value.startsWith('<')) return value;
  try { return decodeURIComponent(value); } catch (err) { return ''; }
}

function emoticonAnnouncement(shortcut, msnobj) {
  if (!shortcut || /[\t\r\n]/.test(shortcut) || !msnobj || /[\r\n]/.test(msnobj)) {
    throw new Error('bad emoticon announcement');
  }
  return shortcut + '\t' + msnobj;
}

function matchingShortcuts(text, catalog) {
  return (catalog || []).filter(item => {
    const shortcut = item && item.shortcut;
    if (!shortcut) return false;
    let from = 0;
    while (from <= text.length) {
      const index = text.indexOf(shortcut, from);
      if (index < 0) return false;
      const before = index === 0 ? '' : text[index - 1];
      const after = text[index + shortcut.length] || '';
      if (!/[A-Za-z0-9_]/.test(before) && !/[A-Za-z0-9_]/.test(after)) return true;
      from = index + 1;
    }
    return false;
  });
}

function announcementsFor(text, catalogPath) {
  if (!catalogPath) return [];
  let catalog;
  try { catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8')); }
  catch (err) { return []; }
  return matchingShortcuts(text, catalog.emoticons || [])
    .filter(item => item.msnobj)
    .map(item => emoticonAnnouncement(item.shortcut, item.msnobj));
}

module.exports = {
  chgLine, uuxCommand, decodeScene, emoticonAnnouncement,
  matchingShortcuts, announcementsFor,
};
