"""Run database migrations and bootstrap data without starting the server."""

import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import create_app


def main():
    print("[MIGRATION] Starting database initialization and migrations...")
    create_app(init_db=True)
    print("[MIGRATION] Done.")


if __name__ == "__main__":
    main()
