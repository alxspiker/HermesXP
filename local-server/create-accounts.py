"""Create the two local MSN accounts (owner + bot), non-interactively.

Mirrors upstream script/user.py set_passwords() but takes passwords from
arguments/secrets instead of getpass (which reads /dev/tty and cannot run
unattended). Idempotent: existing users keep their password and are skipped.

Writes credentials:
  - ~/.hermes/.env (gateway): HERMES_MSN_OWNER_EMAIL, HERMES_MSN_ALLOWED_USERS,
    MSN_BOT_EMAIL, MSN_BOT_PASSWORD, MSN_SERVER_HOST, MSN_LOGIN_URL
  - ~/.hermes/msn-bridge.env (bridge service): MSN_BOT_EMAIL, MSN_BOT_PASSWORD,
    HERMES_MSN_BRIDGE_TOKEN (copied from .env if present), HERMES_MSN_OWNER_EMAIL,
    MSN_SERVER_HOST, MSN_LOGIN_URL
Prints the owner password ONCE (only when the owner account is newly created)
so Alx can type it into WLM on the XP. Never write it to a file or log.

Run from the server directory with the server venv python.
Usage: python create-accounts.py [--reset-owner-password]
"""
import os
import secrets
import sys

sys.path.insert(0, os.getcwd())  # script lives in the repo, modules in the server dir

OWNER_EMAIL = "alx@hermes.local"
OWNER_USERNAME = "alx"
BOT_EMAIL = "hermes-bot@hermes.local"
BOT_USERNAME = "hermes-bot"
LAN_IP = "192.168.1.81"


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


def main():
    from util import misc, hash as hashmod
    from core.db import User
    from core.conn import Conn
    import settings

    reset_owner = "--reset-owner-password" in sys.argv
    conn = Conn(settings.DB)
    owner_pw = None
    bot_pw = None
    with conn.session() as sess:
        for email, username, is_owner in (
            (OWNER_EMAIL, OWNER_USERNAME, True),
            (BOT_EMAIL, BOT_USERNAME, False),
        ):
            user = sess.query(User).filter(User.email == email).one_or_none()
            if user is None:
                pw = secrets.token_urlsafe(16)
                user = User(
                    uuid=misc.gen_uuid(), email=email, username=username,
                    verified=False, friendly_name=email, groups={}, settings={},
                )
                user.password = hashmod.hasher.encode(pw)
                sess.add(user)
                print(f"created user {email}")
                if is_owner:
                    owner_pw = pw
                else:
                    bot_pw = pw
            elif is_owner and reset_owner:
                pw = secrets.token_urlsafe(16)
                user.password = hashmod.hasher.encode(pw)
                sess.add(user)
                owner_pw = pw
                print(f"owner password reset for {email}")
            else:
                print(f"user {email} already exists, password unchanged")

    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    env_path = os.path.join(hermes_home, ".env")
    bridge_env_path = os.path.join(hermes_home, "msn-bridge.env")

    # Bot password: read back from .env if the bot already existed, else use
    # the one just created; if neither exists something is wrong.
    existing = {}
    if os.path.exists(env_path):
        for line in open(env_path):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                existing[k.strip()] = v.strip()
    if bot_pw is None:
        bot_pw = existing.get("MSN_BOT_PASSWORD")
    if not bot_pw:
        print("ERROR: no bot password available", file=sys.stderr)
        sys.exit(1)

    _upsert_env(env_path, {
        "HERMES_MSN_OWNER_EMAIL": OWNER_EMAIL,
        "HERMES_MSN_ALLOWED_USERS": OWNER_EMAIL,
        "MSN_BOT_EMAIL": BOT_EMAIL,
        "MSN_BOT_PASSWORD": bot_pw,
        "MSN_SERVER_HOST": "127.0.0.1",
        "MSN_LOGIN_URL": "http://127.0.0.1:8081/login",
    })
    bridge_token = existing.get("HERMES_MSN_BRIDGE_TOKEN", "")
    bridge_values = {
        "MSN_BOT_EMAIL": BOT_EMAIL,
        "MSN_BOT_PASSWORD": bot_pw,
        "HERMES_MSN_OWNER_EMAIL": OWNER_EMAIL,
        "MSN_SERVER_HOST": "127.0.0.1",
        "MSN_LOGIN_URL": "http://127.0.0.1:8081/login",
    }
    if bridge_token:
        bridge_values["HERMES_MSN_BRIDGE_TOKEN"] = bridge_token
    _upsert_env(bridge_env_path, bridge_values)

    if owner_pw:
        # Printed once for Alx to type into WLM. Never stored anywhere else.
        print(f"OWNER_PASSWORD_FOR_WLM={owner_pw}")
    print("accounts ready")


if __name__ == "__main__":
    main()
