"""Manage MSN users on the local server: add, delete, list.

Bots each get their own MSN user, created and deleted with this tool — the
installer only creates the default owner + bot. Use it to test the bot
lifecycle: add a second bot, verify it can sign in, delete it, verify its
profile is gone and it can no longer sign in.

  add <email>     Create the user with a random password; print it once.
  delete <email>  Delete the user row (and its contact rows). Refuses to
                  delete the configured owner or the configured bridge bot
                  unless --force is given.
  list            Print every user (email, username, verified).

The password is printed once on add; it is never written to a file by this
tool (the bridge's own password lives in ~/.hermes/msn-bridge.env, managed
by ensure-bot-user.py / create-accounts.py).

Run from the server directory with the server venv python.
Usage: python manage-bots.py <add|delete|list> [email] [--force]
"""
import argparse
import os
import secrets
import sys

sys.path.insert(0, os.getcwd())  # script lives in the repo, modules in the server dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["add", "delete", "list"])
    parser.add_argument("email", nargs="?")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from util import misc, hash as hashmod
    from core.db import User, UserContact
    from core.conn import Conn
    import settings

    conn = Conn(settings.DB)

    if args.command == "list":
        with conn.session() as sess:
            for u in sess.query(User).order_by(User.email).all():
                print(f"{u.email}\t{u.username}\tverified={u.verified}")
        return

    email = (args.email or "").strip().lower()
    if not email or "@" not in email:
        print("ERROR: give an email address", file=sys.stderr)
        sys.exit(2)

    if args.command == "add":
        with conn.session() as sess:
            if sess.query(User).filter(User.email == email).one_or_none():
                print(f"user {email} already exists")
                return
            pw = secrets.token_urlsafe(16)
            user = User(
                uuid=misc.gen_uuid(), email=email,
                username=email.split("@", 1)[0],
                verified=False, friendly_name=email, groups={}, settings={},
            )
            user.password = hashmod.hasher.encode(pw)
            sess.add(user)
        # Printed once for the caller to use (e.g. a test login).
        print(f"created user {email}")
        print(f"PASSWORD_FOR_{email}={pw}")
        return

    # delete
    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    env_path = os.path.join(hermes_home, ".env")
    protected = set()
    if os.path.exists(env_path):
        for line in open(env_path):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                if k.strip() in ("HERMES_MSN_OWNER_EMAIL", "MSN_BOT_EMAIL"):
                    protected.add(v.strip().lower())
    if email in protected and not args.force:
        print(f"ERROR: {email} is the configured owner or bridge bot; use --force to delete it", file=sys.stderr)
        sys.exit(3)
    with conn.session() as sess:
        user = sess.query(User).filter(User.email == email).one_or_none()
        if user is None:
            print(f"user {email} does not exist")
            return
        sess.query(UserContact).filter(
            (UserContact.user_id == user.id) | (UserContact.contact_id == user.id)
        ).delete(synchronize_session=False)
        sess.delete(user)
    print(f"deleted user {email} (profile and contact rows removed)")


if __name__ == "__main__":
    main()
