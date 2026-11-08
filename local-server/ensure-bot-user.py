"""Ensure the configured MSN bot user exists on the local server.

Every bot gets its own MSN user, created automatically — no account is
hardcoded here. Reads ``MSN_BOT_EMAIL`` from the environment (the bridge
service gets it from its EnvironmentFile). If the user does not exist, it
is created with a random password; if it exists but no password is
configured in the env files, the password is reset. The password is written
to ``~/.hermes/msn-bridge.env`` and ``~/.hermes/.env`` (``MSN_BOT_PASSWORD``).

Run before the bridge starts (systemd ExecStartPre on the bridge service),
or manually. The bridge service re-reads the env file at ExecStart, so a
password written here is picked up by the bridge on the same start.

Usage: <venv>/bin/python ensure-bot-user.py [server-dir]
  server-dir defaults to ~/.hermes/msn-server.

Also makes sure the bot shows up in the owner's Messenger contact list
(and the owner in the bot's), so the user just signs in, picks the bot,
and starts talking — no manual contact adding. Both directions use the
Forward + Allow lists (FL|AL = 0x03). Idempotent: rows are only inserted
when missing.
"""
import os
import secrets
import sys

DEFAULT_SERVER_DIR = os.path.expanduser("~/.hermes/msn-server")


def _read_env_file(path):
    values = {}
    if os.path.exists(path):
        for line in open(path):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                values[k.strip()] = v.strip()
    return values


def _upsert_env(path, values):
    lines = []
    if os.path.exists(path):
        with open(path) as f:
            lines = [l.rstrip("\n") for l in f]
    out = []
    seen = set()
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in values.items():
        if key not in seen:
            out.append(f"{key}={val}")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(path, 0o600)


def _owner_email(hermes_home):
    email = (os.environ.get("HERMES_MSN_OWNER_EMAIL") or "").strip()
    if email:
        return email
    vals = _read_env_file(os.path.join(hermes_home, ".env"))
    email = (vals.get("HERMES_MSN_OWNER_EMAIL") or "").strip()
    return email or "user@hermes.local"


def ensure_contacts(conn, owner_email, bot_email):
    """Insert the owner<->bot contact rows (FL|AL) when missing."""
    from core.db import User, UserContact

    FL_AL = 0x03  # Forward list + Allow list: visible, can message
    with conn.session() as sess:
        owner = sess.query(User).filter(User.email == owner_email).one_or_none()
        bot = sess.query(User).filter(User.email == bot_email).one_or_none()
        if owner is None or bot is None:
            print(f"contacts: owner or bot user missing "
                  f"(owner={owner is not None}, bot={bot is not None})")
            return
        for user, contact in ((owner, bot), (bot, owner)):
            row = sess.query(UserContact).filter(
                UserContact.user_id == user.id,
                UserContact.contact_id == contact.id,
            ).one_or_none()
            if row is None:
                row = UserContact(
                    user_id=user.id, contact_id=contact.id,
                    user_uuid=user.uuid, uuid=contact.uuid,
                    name=contact.friendly_name or contact.email,
                    lists=FL_AL, pending=False, groups=[],
                    is_messenger_user=True, index_id="0",
                )
                sess.add(row)
                print(f"contacts: added {contact.email} "
                      f"to {user.email}'s list")
            else:
                print(f"contacts: {contact.email} already in "
                      f"{user.email}'s list")


def main():
    server_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERVER_DIR
    sys.path.insert(0, server_dir)
    os.chdir(server_dir)

    from util import misc, hash as hashmod
    from core.db import User
    from core.conn import Conn
    import settings

    bot_email = (os.environ.get("MSN_BOT_EMAIL") or "").strip()
    if not bot_email or "@" not in bot_email:
        print("ERROR: MSN_BOT_EMAIL is not set", file=sys.stderr)
        sys.exit(2)

    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    env_path = os.path.join(hermes_home, ".env")
    bridge_env_path = os.path.join(hermes_home, "msn-bridge.env")
    existing = _read_env_file(bridge_env_path) or _read_env_file(env_path)

    conn = Conn(settings.DB)
    created = False
    with conn.session() as sess:
        user = sess.query(User).filter(User.email == bot_email).one_or_none()
        if user is None:
            pw = secrets.token_urlsafe(16)
            user = User(
                uuid=misc.gen_uuid(), email=bot_email,
                username=bot_email.split("@", 1)[0],
                verified=False, friendly_name=bot_email, groups={}, settings={},
            )
            user.password = hashmod.hasher.encode(pw)
            sess.add(user)
            created = True
            print(f"created bot user {bot_email}")
        else:
            print(f"bot user {bot_email} already exists")
            pw = None

    # Password: use the newly created one, else the configured one; if the
    # user exists but no password is configured anywhere, reset it.
    pw = pw or existing.get("MSN_BOT_PASSWORD")
    if not pw:
        from core.db import User as _User
        pw = secrets.token_urlsafe(16)
        with conn.session() as sess:
            user = sess.query(_User).filter(_User.email == bot_email).one()
            user.password = hashmod.hasher.encode(pw)
            sess.add(user)
        print(f"reset password for bot user {bot_email}")
    _upsert_env(bridge_env_path, {"MSN_BOT_EMAIL": bot_email, "MSN_BOT_PASSWORD": pw})
    _upsert_env(env_path, {"MSN_BOT_EMAIL": bot_email, "MSN_BOT_PASSWORD": pw})
    print(f"bot user ready: {bot_email} (created={created})")
    ensure_contacts(conn, _owner_email(hermes_home), bot_email)


if __name__ == "__main__":
    main()
