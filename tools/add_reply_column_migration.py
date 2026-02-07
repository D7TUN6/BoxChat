"""
Migration helper: add `reply_to_id` column to `message` table.

This script targets SQLite (the default for the project). It will:
- read the `SQLALCHEMY_DATABASE_URI` from project `config.py`
- if it's a SQLite DB file, connect and check whether `reply_to_id` exists
- if not present, run `ALTER TABLE message ADD COLUMN reply_to_id INTEGER` (nullable)
- verify success and print instructions

Run from project root:
    python3 tools/add_reply_column_migration.py

This avoids Alembic and performs a safe, additive change (nullable column).
"""

import os
import sys
import sqlite3

try:
    # Import project config to read DB URI
    # Ensure project path is on sys.path (script run from repo root)
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import config
except Exception as e:
    print('Failed to import project config:', e)
    sys.exit(1)

uri = getattr(config, 'SQLALCHEMY_DATABASE_URI', None)

# Allow overriding DB path via CLI arg or BOXCHAT_DB env var (path to sqlite file)
override_path = None
if len(sys.argv) > 1:
    override_path = sys.argv[1]
elif os.environ.get('BOXCHAT_DB'):
    override_path = os.environ.get('BOXCHAT_DB')
if not uri:
    print('No SQLALCHEMY_DATABASE_URI found in config. Aborting.')
    sys.exit(1)

if not uri.startswith('sqlite:') and not override_path:
    print('This script currently only supports SQLite URIs. Detected:', uri)
    print('For other databases, please run an ALTER TABLE statement appropriate for your DB:')
    print("  ALTER TABLE message ADD COLUMN reply_to_id INTEGER;")
    sys.exit(1)

# Parse sqlite path (handle sqlite:///relative.db and sqlite:////absolute.db)
file_path = None
if override_path:
    file_path = override_path
else:
    file_path = uri.split('sqlite:///')[-1]
file_path = file_path.strip()
if not file_path:
    print('Could not determine sqlite DB file path from URI:', uri)
    sys.exit(1)

# If path is relative, make it relative to repo root
if not os.path.isabs(file_path):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    file_path = os.path.normpath(os.path.join(repo_root, file_path))

print('SQLite DB file resolved to:', file_path)
if not os.path.exists(file_path):
    print('Warning: DB file does not exist yet. If you create it later, run this script again to add the column.')
    sys.exit(0)

try:
    conn = sqlite3.connect(file_path)
    cur = conn.cursor()

    # Check table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message';")
    row = cur.fetchone()
    if not row:
        print('Table `message` not found in database. Aborting.')
        conn.close()
        sys.exit(1)

    # Check if column already exists
    cur.execute("PRAGMA table_info(message);")
    cols = [r[1] for r in cur.fetchall()]
    if 'reply_to_id' in cols:
        print('Column `reply_to_id` already exists — nothing to do.')
        conn.close()
        sys.exit(0)

    # Add column (nullable integer) — additive and safe
    print('Adding column `reply_to_id` to `message` table...')
    cur.execute('ALTER TABLE message ADD COLUMN reply_to_id INTEGER;')
    conn.commit()

    # Verify
    cur.execute("PRAGMA table_info(message);")
    cols_after = [r[1] for r in cur.fetchall()]
    if 'reply_to_id' in cols_after:
        print('Migration applied successfully. Column `reply_to_id` is now present.')
    else:
        print('Migration reported success but column not found. Please inspect DB manually.')

    conn.close()
    print('\nNext steps:')
    print('- Restart your app so SQLAlchemy sees the updated schema (restart server).')
    print('- New messages with reply_to will be saved and replies persisted.')
    print('- Existing messages are unchanged; you can manually populate `reply_to_id` if you need retroactive linking.')

except Exception as e:
    print('Migration failed:', e)
    try:
        conn.close()
    except Exception:
        pass
    sys.exit(1)
