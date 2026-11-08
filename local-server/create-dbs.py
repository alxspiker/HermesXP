"""Create the msn-server SQLite databases.

Upstream script/dbcreate.py runs SQLAltery migrations after create_all, and
that migration step fails on modern SQLAlchemy (ValueError: can't find Table
't_user'). create_all alone is enough for a fresh install, so this script
does only that. Safe to re-run.
Run from the server directory with the server venv python.
"""
import os
import sys
sys.path.insert(0, os.getcwd())  # script lives in the repo, modules in the server dir
from core import db, stats
from core.conn import Conn
import settings

conn_db = Conn(settings.DB)
db.Base.metadata.create_all(conn_db.engine)
conn_stats = Conn(settings.STATS_DB)
stats.Base.metadata.create_all(conn_stats.engine)
print("databases ready")
