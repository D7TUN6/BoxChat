#!/usr/bin/env python3
"""
Simple migration script to add presence columns to the `user` table for SQLite.
Usage:
    python3 tools/add_presence_migration.py

This script is safe to run multiple times: it checks for existing columns before ALTER TABLE.
It supports SQLite URIs like `sqlite:///thecomboxmsgr.db` configured in `config.py`.
If your app uses another DB (Postgres/MySQL), don't run this script; use your migration tooling.
"""
import os
import sqlite3
import sys

# Ensure project root is on sys.path so `app` package can be imported when running
# this script from the `tools/` directory or elsewhere.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config


def get_sqlite_path(uri):
    if not uri:
        return None
    if uri.startswith('sqlite:///'):
        p = uri[len('sqlite:///'):]
        # If the path begins with a slash it's already absolute
        if p.startswith('/'):
            return os.path.abspath(p)

        # Otherwise try a few likely locations: project root, instance/ subfolder, or fallback
        # PROJECT_ROOT is the repo root (set at module import)
        candidates = [
            os.path.join(PROJECT_ROOT, p),
            os.path.join(PROJECT_ROOT, 'instance', p),
            os.path.join(PROJECT_ROOT, 'instance', os.path.basename(p)),
            os.path.join(PROJECT_ROOT, os.path.basename(p)),
        ]
        for c in candidates:
            if os.path.exists(c):
                return os.path.abspath(c)

        # Fallback to project-root relative path
        return os.path.abspath(os.path.join(PROJECT_ROOT, p))
    return None


def column_exists(conn, table, column):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    rows = cur.fetchall()
    cols = [r[1] for r in rows]
    return column in cols


def main():
    uri = getattr(config, 'SQLALCHEMY_DATABASE_URI', None)
    db_path = get_sqlite_path(uri)
    if not db_path:
        print("Unsupported or missing SQLALCHEMY_DATABASE_URI: expected sqlite:///...\nValue:", uri)
        sys.exit(1)

    print(f"Using SQLite DB at: {db_path}")
    if not os.path.exists(db_path):
        print("Database file not found. Make sure the app has already created it or run the app once to create DB.")
        sys.exit(1)

    # Backup suggestion
    try:
        bak = db_path + '.bak'
        if not os.path.exists(bak):
            open(bak, 'wb').write(open(db_path, 'rb').read())
            print(f"Backup created at: {bak}")
        else:
            print(f"Backup already exists at: {bak}")
    except Exception as e:
        print("Warning: failed to create backup:", e)

    conn = sqlite3.connect(db_path)
    try:
        # presence_status TEXT DEFAULT 'offline'
        if not column_exists(conn, 'user', 'presence_status'):
            print("Adding column: presence_status TEXT DEFAULT 'offline'")
            conn.execute("ALTER TABLE user ADD COLUMN presence_status TEXT DEFAULT 'offline'")
        else:
            print('Column presence_status already exists')

        # last_seen DATETIME (nullable)
        if not column_exists(conn, 'user', 'last_seen'):
            print('Adding column: last_seen DATETIME')
            conn.execute("ALTER TABLE user ADD COLUMN last_seen DATETIME")
        else:
            print('Column last_seen already exists')

        # hide_status INTEGER DEFAULT 0
        if not column_exists(conn, 'user', 'hide_status'):
            print("Adding column: hide_status INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE user ADD COLUMN hide_status INTEGER DEFAULT 0")
        else:
            print('Column hide_status already exists')

        conn.commit()
        print('Migration finished successfully.')
    except Exception as e:
        print('Migration failed:', e)
        conn.rollback()
        sys.exit(2)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
