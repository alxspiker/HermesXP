var net = require('net');
const crypto = require('crypto');
var msnsocket = require('./MSNHelper.js');
const { MSNPFrameDecoder } = require('./frame.js');
const { p2pPayload } = require('../file_transfer.js');
const presence = require('../wlm_presence.js');
const { loginSSO } = require('./sso.js');
const axios = require('axios');
const https = require('https');
const EventEmitter = require('events');
var os = require('os');
const { NOTINITIALIZED } = require('dns');
const internal = require('stream');

// HermesXP local-server patch (see LOCAL-PATCH.md):
// the NS host and the Passport login URL are taken from the environment so
// the client can talk to a local server instead of Escargot. Defaults keep
// the original Escargot behaviour when the variables are unset.
const MSN_SERVER_HOST = process.env.MSN_SERVER_HOST || 'msnmsgr.escargot.chat';
const MSN_LOGIN_URL = process.env.MSN_LOGIN_URL || 'https://msnmsgr.escargot.chat/login';
// MSN_LOGIN_INSECURE=1: accept a self-signed/local-CA cert on an https login
// URL (only for a local server; never for Escargot).
const MSN_LOGIN_INSECURE = process.env.MSN_LOGIN_INSECURE === '1';
const MSN_PROTOCOL = process.env.MSN_BOT_PROTOCOL === '18' ? 'MSNP18' :
                     process.env.MSN_BOT_PROTOCOL === '13' ? 'MSNP13' : 'MSNP9';
// MSNP13 is required for UUN / UBN (tunneled SIP); default remains MSNP9
// until the native-call feature is explicitly enabled and verified.
const MSN_NATIVE_CALL = MSN_PROTOCOL !== 'MSNP9';
// MSNC4 + SIP invites + tunneled SIP. Never advertise codecs unsupported by
// the actual call engine. WLM 2009 may require MSNP16 SSO capabilities.
const MSN_NATIVE_CAPS = 0x40300000;

const endTag = "\r\n";

class MSNClient extends EventEmitter  {
	constructor(login, password) {
		super();
		this.login = login;
		this.password = password;

		this.token = '';
		this.TrID = 0;
		this.email = '';
		this.name = '';
		this.client = new net.Socket();

		this.active = false;

		this.switchboard = [];
		this.frameDecoder = new MSNPFrameDecoder();
		this.machineGuid = '{' + crypto.randomUUID().toUpperCase() + '}';
	}

	_chg(trid, status, caps) {
		this.client.write(presence.chgLine(
			String(trid), status, String(caps), process.env.MSN_BOT_MSNOBJ || ''));
	}

	_advertiseScene() {
		const scene = presence.decodeScene(process.env.MSN_BOT_SCENE || '');
		if (!scene) return;
		this.TrID++;
		this.client.write(presence.uuxCommand(String(this.TrID), this.machineGuid, scene));
	}

	execute() {
		this.client.connect(1863, MSN_SERVER_HOST, () => {
			console.log('[DEBUG] Connected to MSN Server');
			this.client.write('VER 0 ' + MSN_PROTOCOL + ' CVR0' + endTag);
		});

		this.client.on('data', async data => {
			this.TrID++;
			let frames;
			try { frames = this.frameDecoder.feed(data); }
			catch (err) { this.emit('error', err); this.client.destroy(); return; }
			let parsed = frames.map(frame => frame.words);
			// Do not print UBN SIP/SDP payloads (which may contain IP addresses).
			if (process.env.MSN_DEBUG === '1') console.log(parsed);
			for (const frame of frames) {
			  if (frame.command === 'UBN' && frame.words.length >= 4) {
			    const sender = frame.words[1].split(';')[0].trim().toLowerCase();
			    this.emit('native_signal', {
			      sender, type: Number(frame.words[2]), payload: frame.body,
			    });
			  }
			}
			if(parsed != undefined) {
				parsed.forEach(async element => {
					if(element[0] == 'VER' && element[2] == MSN_PROTOCOL) {
						console.log('[DEBUG] System info sent')
						this.client.write('CVR 2 0x0409 '+process.platform+' '+os.version+' '+process.arch+' NODEMSN 5.0.0544 MSMSGS ' + this.login + endTag);
					}

					if(element[0] == 'CVR') {
						console.log('[DEBUG] [AUTH] Trying to log in...')
						this.client.write('USR 3 ' + (MSN_PROTOCOL === 'MSNP18' ? 'SSO' : 'TWN') + ' I ' + this.login + endTag);
					}

					if(element[0] === 'USR' && element[2] === 'SSO' && element[3] === 'S'){
						try{
						  const proof = await loginSSO('http://127.0.0.1:8081/RST2.srf',
						    this.login, this.password, element[5]);
						  this.client.write('USR 4 SSO S ' + proof.token + ' ' + proof.proof +
						    ' ' + this.machineGuid + endTag);
						  this._chg(5, 'NLN', MSN_NATIVE_CAPS + ':0');
					  this._advertiseScene();
						} catch(error){
						  this.emit('error',new Error('MSNP18 SSO login failed: '+error.message));
						  this.client.destroy();
						}
					}

					if(element[0] == 'USR' && element[2] == 'TWN'){
						console.log('[DEBUG] [AUTH] Connecting to Nexus');
						let tokenu = '';
						await axios.get(MSN_LOGIN_URL, {
							...(MSN_LOGIN_INSECURE ? {httpsAgent: new https.Agent({rejectUnauthorized: false})} : {}),
							headers:{"Authorization":"Passport1.4 OrgVerb=GET,OrgURL=http%3A%2F%2Fmessenger%2Emsn%2Ecom,sign-in=" + this.login + ",pwd=" + this.password + ",ct=1,rver=1,wp=FS_40SEC_0_COMPACT,lc=1,id=1"}
						})
							.then(Response => {
								tokenu = Response.headers['authentication-info'];
								this.token = msnsocket.parseToken(tokenu);
								if (this.token == 'failed') {
									console.log('[DEBUG] [AUTH] Incorrect login or password');
									this.emit('msg', {'type': 'auth_failed'});
									this.client.destroy();
									delete this;
								}else{
									console.log('[DEBUG] [AUTH] Success');
								}
								
							})
							.catch(err => console.log('error ', this.emit(err)));
						this.client.write('USR 4 TWN S ' + this.token + endTag);
						this._chg(5, 'NLN', (MSN_NATIVE_CALL ? MSN_NATIVE_CAPS : 0));
						this._advertiseScene();
						this.TrID = 6;
						this.active = true;
					}

					if(element[0] == 'USR' && element[2] == 'OK'){
						this.email = element[3];
						this.name = element[4];
						this.active = true;
						this.emit('msg', {'type': 'connected'});
					}

					if(element[0] == 'RNG' && element[3] == 'CKI') {
						console.log('[DEBUG] Accepting request');
						let server = new String(element[2]).split(':');
						// A previous session with this user may have gone stale: the
						// old cleanup deleted on msg.type == 'bye', but
						// parseMessageSB reports BYE as 'leftChat', so the stale
						// switchboard was never removed and later invites were
						// ignored by the `== undefined` guard. Always start a
						// fresh switchboard for a new invite.
						if (this.switchboard[element[5]] != undefined) {
							try { this.switchboard[element[5]].switchboard.destroy(); } catch (e) {}
							delete this.switchboard[element[5]];
						}
						this.switchboard[element[5]] = new MSNSwitchBoard(server[0], server[1], element[5], this.email);
						this.switchboard[element[5]].execute();
						this.switchboard[element[5]].on('connected', () => {this.switchboard[element[5]].acceptRequest(element[1], element[4]);})
					
						this.switchboard[element[5]].on('msg', msg => {
							if (msg != undefined) {
								this.emit('msg', msg);
								if(msg.type == 'bye' || msg.type == 'leftChat') {
									delete this.switchboard[element[5]];	
								}
							}
						});
					}

					if(element[0] == 'OUT') {
						console.log('[DEBUG] Exit requested by server');
						this.client.destroy();
						delete this;
						this.emit('close');
					}

					// Errors
					
					if(element[0] == '911') {
						if(this.active == false) {
							console.log('[DEBUG] [AUTH] Incorrect login or password');
							this.emit('msg', {'type': 'auth_failed'});
							this.client.destroy();
							delete this;
						}
					}
				});
			}
		});

		this.client.on('close', () => {
			this.emit('close');
			this.active = false;
		});

	}

	getUserInfo() {
		return {'active': this.active,
				'email': this.email,
				'name': this.name};
	}

	sendNativeSignal(recipient, type, payload) {
		if (!MSN_NATIVE_CALL || !this.active || !this.email)
			throw new Error('MSNP13 native signaling is not connected');
		if (!/^[a-z0-9_.+\-]+@[a-z0-9.\-]+$/i.test(recipient))
			throw new Error('Invalid native signaling recipient');
		if (!Number.isInteger(type) || type < 0 || type > 16)
			throw new Error('Invalid UUN type');
		if (!Buffer.isBuffer(payload) || !payload.length || payload.length > 16384)
			throw new Error('Native signaling payload exceeds 16 KiB');
		this.TrID++;
		const header = Buffer.from('UUN ' + this.TrID + ' ' + recipient + ' ' + type +
		                           ' ' + payload.length + '\r\n');
		this.client.write(Buffer.concat([header, payload]));
	}

	sendP2P(email, p2pBuffer) {
		const board = this.switchboard[email];
		if (!board || !board.switchboard || board.switchboard.destroyed)
			throw new Error('switchboard not open');
		board.sendP2P(email, p2pBuffer);
	}

	async sendMessage(emailArg, bodyArg) {
		if(this.active == true) {
			if(this.switchboard[emailArg] != null && !this.switchboard[emailArg].switchboard.destroyed) {
				this.switchboard[emailArg].sendMessage(bodyArg);
			} else {
				this.TrID++;
				this.client.write('XFR ' + this.TrID +' SB' + endTag);
				this.client.on('data', data => {
					let parsed = msnsocket.parseMessage(data);
					console.log(parsed);
					if(parsed != undefined) {
						parsed.forEach(async element => {
							if(element[0] == 'XFR' && element[2] == 'SB') {
								let server = new String(element[3]).split(':');
								this.switchboard[emailArg] = new MSNSwitchBoard(server[0], server[1], emailArg, this.email);
								this.switchboard[emailArg].execute();
								this.switchboard[emailArg].authorizeAndSendMessage(element[5], bodyArg);
							}
						});
					}
				});
			}
		}
	}
	
	/**
	 * This function will change the Presence of profile.
	 * 
	 * @param {MSNStatuses} status The Status
	 */
	async changePresence(status) {
		/*
			Use MSNStatuses const 

			Statuses:
			NLN - Available
			BSY - Busy
			IDL - Idle
			BRB - Be Right Back
			AWY - Away
			PHN - On the Phone
			LUN - Out to Lunch
		*/
		if(this.active == true) {
			this._chg(this.TrID, status, '0');
		}
	}

	listContacts(callback) {
		if(this.active == true) {
			let contactList = [];
			let contactListCount = 0;
			
			let contactListCountTmp = 1;
			this.client.write('SYN 1 0' + endTag);
			this.client.on('data', data => {
				this.TrID++;
				let parsed = msnsocket.parseMessage(data);
				if(parsed != undefined) {
					parsed.forEach(element => {
						if (element[0] == 'SYN' && element[1] == '1' && element[2] == '1') {
							contactListCount = parseInt(element[3]);
						} else if (element[0] == 'LST') {
							contactListCountTmp++;
							if (contactListCountTmp <= contactListCount) {
								let contact = {email: element[1], name: decodeURI(element[2])};
								contactList.push(contact);
							}
						}
					});
				}

				if(contactList.length+1 == contactListCount) {
					callback(contactList);
				}
			});
		}
	}
};

class MSNSwitchBoard extends EventEmitter {
	constructor(server, port, email, selfEmail) {
		super();
		this.email = email;
		this.selfEmail = selfEmail;
		this.server = server;
		this.port = port;
		this.TrID = 0;
		this.switchboard = new net.Socket();
		this.frameDecoder = new MSNPFrameDecoder();
		this.ThreadID = Math.random()*0.001;

		// Temp
		this.tmpMessage = '';

		console.log('[DEBUG] [SWITCHBOARD: ' + this.ThreadID + '] Created');
	}

	execute() {
		this.switchboard.connect(this.port, this.server, () => {
			console.log('[DEBUG] [SWITCHBOARD: ' + this.ThreadID + '] Connected to Switchboard Server');
			this.emit('connected');
		});

		this.switchboard.on('data',  data => {
			let frames;
			try { frames = this.frameDecoder.feed(data); }
			catch (err) {
				console.error('[DEBUG] [SWITCHBOARD] frame error:', err.message);
				this.switchboard.destroy();
				return;
			}
			for (const frame of frames) {
				this.TrID++;
				if (frame.command === 'MSG') {
					const p2p = p2pPayload(frame.body);
					if (p2p) {
						this.emit('msg', {type: 'p2p', user: this.email, payload: p2p});
						continue;
					}
					if (legacyFileInvite(frame.body)) {
						const split = frame.body.indexOf('\r\n\r\n');
						this.emit('msg', {
							type: 'file_invite',
							user: this.email,
							body: split >= 0 ? frame.body.subarray(split + 4).toString('utf8') : '',
						});
						continue;
					}
					const raw = Buffer.concat([
						Buffer.from(frame.words.join(' ') + '\r\n', 'utf8'), frame.body]);
					const parsed = msnsocket.parseMessageSB(raw.toString('utf8'), this.email);
					if (parsed) this.emit('msg', parsed);
					continue;
				}
				const parsed = msnsocket.parseMessageSB(frame.words.join(' ') + '\r\n', this.email);
				if (!parsed) continue;
				if (process.env.MSN_DEBUG === '1')
					console.log('[DEBUG] [SWITCHBOARD] event type:', parsed.type);
				if (parsed.type == 'joinedChat') {
					this.sendMessage(this.tmpMessage);
				} else if (parsed.type == 'authSuccess') {
					console.log('CAL ' + this.TrID + ' ' + this.email + endTag);
					this.switchboard.write('CAL ' + this.TrID + ' ' + this.email + endTag);
				} else {
					this.emit('msg', parsed);
				}
			}
		});
		
		this.switchboard.on('error', err => {
			console.log(err);
		})
	}

	acceptRequest(session, auth) {
		this.switchboard.write('ANS 1 '+this.selfEmail+' '+auth+' '+session+ endTag);
	}

	authorizeAndSendMessage(token, body) {
		this.switchboard.write('USR ' + this.TrID + ' ' + this.selfEmail + ' ' + token + endTag);
		this.tmpMessage = body;
	}

	sendP2P(dest, p2pBuffer) {
		if (!/^[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+$/.test(dest))
			throw new Error('invalid P2P recipient');
		if (!Buffer.isBuffer(p2pBuffer) || p2pBuffer.length < 48 || p2pBuffer.length > 16384)
			throw new Error('invalid P2P payload');
		this.TrID++;
		const mime = Buffer.from(
			'MIME-Version: 1.0\r\nContent-Type: application/x-msnmsgrp2p\r\n' +
			'P2P-Dest: ' + dest + '\r\n\r\n');
		const body = Buffer.concat([mime, p2pBuffer]);
		this.switchboard.write(Buffer.concat([
			Buffer.from('MSG ' + this.TrID + ' D ' + body.length + '\r\n'), body]));
	}

	sendMessage(body) {
		const announcements = presence.announcementsFor(
			body, process.env.MSN_BOT_EMOTICON_CATALOG);
		for (const announcement of announcements) {
			this._writePayload('text/x-mms-emoticon', announcement, false);
		}
		this._writePayload('text/plain; charset=UTF-8', body, true);
	}

	_writePayload(contentType, body, formatted) {
		const format = formatted
			? 'X-MMS-IM-Format: FN=Arial; EF=I; CO=0; CS=0; PF=22'+endTag
			: '';
		let msg = 'MIME-Version: 1.0'+endTag+
				'Content-Type: '+contentType+endTag+
				format+endTag+
				body;
		this.switchboard.write( 'MSG '+this.TrID+' N ' +
								(new TextEncoder().encode(msg)).length + ' ' +
								endTag+msg);
	}
}

// Variables

const MSNStatuses = {
	Avaliable: 'NLN',
	Busy: 'BSY',
	Idle: 'IDL',
	BeRightBack: 'BRB',
	Away: 'AWY',
	OnThePhone: 'PHN',
	OutOfLunch: 'LUN'
}

function legacyFileInvite(body) {
	if (!Buffer.isBuffer(body)) return false;
	const head = body.subarray(0, Math.min(body.length, 1024)).toString('latin1');
	return /content-type:\s*text\/x-msmsgsinvite/i.test(head) &&
		/application-name:\s*file transfer/i.test(head);
}

exports.MSNClient = MSNClient;
exports.MSNSwitchBoard = MSNSwitchBoard;
exports.MSNStatuses = MSNStatuses;
