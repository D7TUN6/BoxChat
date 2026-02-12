"""Run database migrations and bootstrap data without starting the server.

Usage:
  python tools/migration.py
  python tools/migration.py --db ./instance/thecomboxmsgr.db
"""

import argparse
import os
import sys
from types import SimpleNamespace

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config as app_config
from app import create_app


def _sqlite_uri_from_path(db_path: str) -> str:
    abs_db = os.path.abspath(db_path).replace('\\', '/')
    # Windows absolute path: C:/...
    if len(abs_db) > 2 and abs_db[1] == ':':
        return f"sqlite:///{abs_db}"
    # POSIX absolute path: /...
    return f"sqlite:////{abs_db.lstrip('/')}"


def _build_config_for_db(db_path: str):
    values = {k: getattr(app_config, k) for k in dir(app_config) if k.isupper()}
    values['SQLALCHEMY_DATABASE_URI'] = _sqlite_uri_from_path(db_path)
    return SimpleNamespace(**values)


def _default_targets():
    # Prefer migrating legacy instance DB first, then root DB.
    candidates = [
        os.path.join(ROOT_DIR, 'instance', 'thecomboxmsgr.db'),
        os.path.join(ROOT_DIR, 'thecomboxmsgr.db'),
    ]
    existing = [p for p in candidates if os.path.exists(p)]
    return existing if existing else [candidates[0]]


def main():
    parser = argparse.ArgumentParser(description='Run BoxChat DB migrations.')
    parser.add_argument('--db', help='Path to sqlite DB file to migrate')
    args = parser.parse_args()

    targets = [os.path.abspath(args.db)] if args.db else _default_targets()

    print('[MIGRATION] Starting database initialization and migrations...')
    for target in targets:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        cfg = _build_config_for_db(target)
        print(f'[MIGRATION] Applying migrations to: {target}')
        print(f'[MIGRATION] DB URI: {cfg.SQLALCHEMY_DATABASE_URI}')
        create_app(config=cfg, init_db=True)
    print('[MIGRATION] Done.')


if __name__ == '__main__':
    main()
