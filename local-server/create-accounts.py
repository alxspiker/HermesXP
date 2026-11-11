"""Create the two local MSN accounts (owner + bot), non-interactively.

Mirrors upstream script/user.py set_passwords() but takes passwords from
arguments/secrets instead of getpass (which reads /dev/tty and cannot run
unattended). Idempotent: existing users keep their password and are skipped.

No personal details are hardcoded. The owner defaults to ``user@hermes.local``
(username ``user``); the bot defaults to ``hermes-bot@hermes.local`` (a role
name, not a person). Both are overridable, in priority order:
  1. ``--owner-email`` / ``--bot-email`` arguments
  2. ``HERMES_MSN_OWNER_EMAIL`` / ``MSN_BOT_EMAIL`` in the environment or in
     the existing ``~/.hermes/.env`` (an existing .env value always wins, so
     re-running the installer never renames the accounts on a live install)
  3. the defaults above

Writes credentials:
  - ~/.hermes/.env (gateway): HERMES_MSN_OWNER_EMAIL, HERMES_MSN_ALLOWED_USERS,
    MSN_BOT_EMAIL, MSN_BOT_PASSWORD, MSN_SERVER_HOST, MSN_LOGIN_URL
  - ~/.hermes/msn-bridge.env (bridge service): MSN_BOT_EMAIL, MSN_BOT_PASSWORD,
    HERMES_MSN_BRIDGE_TOKEN (copied from .env if present), HERMES_MSN_OWNER_EMAIL,
    MSN_SERVER_HOST, MSN_LOGIN_URL
Prints the owner password ONCE (only when the owner account is newly created)
so it can be typed into WLM on the XP. Never write it to a file or log.

Run from the server directory with the server venv python.
Usage: python create-accounts.py [--owner-email a@b] [--bot-email c@d]
       [--reset-owner-password]
"""
import argparse
import os
import secrets
import string
import sys

sys.path.insert(0, os.getcwd())  # script lives in the repo, modules in the server dir

DEFAULT_OWNER_EMAIL = "user@hermes.local"
DEFAULT_BOT_EMAIL = "hermes-bot@hermes.local"


def new_owner_password():
    """XP WLM 2009 limits entered passwords to 16 characters.

    Use 16 unpredictable alphanumeric characters (~95 bits), without
    truncating or rewriting any existing account credentials.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


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


def bridge_token(existing):
    return existing.get("HERMES_MSN_BRIDGE_TOKEN") or secrets.token_hex(32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-email")
    parser.add_argument("--bot-email")
    parser.add_argument("--reset-owner-password", action="store_true")
    args = parser.parse_args()

    from util import misc, hash as hashmod
    from core.db import User
    from core.conn import Conn
    import settings

    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    env_path = os.path.join(hermes_home, ".env")
    bridge_env_path = os.path.join(hermes_home, "msn-bridge.env")
    existing = _read_env_file(env_path)

    # Existing .env wins (never rename a live install), then CLI, then env,
    # then the generic default.
    owner_email = (
        existing.get("HERMES_MSN_OWNER_EMAIL")
        or args.owner_email
        or os.environ.get("HERMES_MSN_OWNER_EMAIL")
        or DEFAULT_OWNER_EMAIL
    )
    bot_email = (
        existing.get("MSN_BOT_EMAIL")
        or args.bot_email
        or os.environ.get("MSN_BOT_EMAIL")
        or DEFAULT_BOT_EMAIL
    )
    owner_username = owner_email.split("@", 1)[0]
    bot_username = bot_email.split("@", 1)[0]

    conn = Conn(settings.DB)
    owner_pw = None
    bot_pw = None
    with conn.session() as sess:
        for email, username, is_owner in (
            (owner_email, owner_username, True),
            (bot_email, bot_username, False),
        ):
            user = sess.query(User).filter(User.email == email).one_or_none()
            if user is None:
                pw = new_owner_password() if is_owner else secrets.token_urlsafe(16)
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
            elif is_owner and args.reset_owner_password:
                pw = new_owner_password()
                user.password = hashmod.hasher.encode(pw)
                sess.add(user)
                owner_pw = pw
                print(f"owner password reset for {email}")
            else:
                print(f"user {email} already exists, password unchanged")

    # Bot password: read back from .env if the bot already existed, else use
    # the one just created; if neither exists something is wrong.
    if bot_pw is None:
        bot_pw = existing.get("MSN_BOT_PASSWORD")
    if not bot_pw:
        print("ERROR: no bot password available", file=sys.stderr)
        sys.exit(1)

    token = bridge_token(existing)
    _upsert_env(env_path, {
        "HERMES_MSN_BRIDGE_TOKEN": token,
        "HERMES_MSN_OWNER_EMAIL": owner_email,
        "HERMES_MSN_ALLOWED_USERS": existing.get("HERMES_MSN_ALLOWED_USERS") or owner_email,
        "MSN_BOT_EMAIL": bot_email,
        "MSN_BOT_PASSWORD": bot_pw,
        "MSN_SERVER_HOST": "127.0.0.1",
        "MSN_LOGIN_URL": "http://127.0.0.1:8081/login",
    })
    bridge_values = {
        "HERMES_MSN_BRIDGE_TOKEN": token,
        "MSN_BOT_EMAIL": bot_email,
        "MSN_BOT_PASSWORD": bot_pw,
        "HERMES_MSN_OWNER_EMAIL": owner_email,
        "MSN_SERVER_HOST": "127.0.0.1",
        "MSN_LOGIN_URL": "http://127.0.0.1:8081/login",
    }
    _upsert_env(bridge_env_path, bridge_values)

    if owner_pw:
        # Printed once for typing into WLM. Never stored anywhere else.
        print(f"OWNER_PASSWORD_FOR_WLM={owner_pw}")
    print("accounts ready")


if __name__ == "__main__":
    main()
