from sqlalchemy import inspect, text


def ensure_schema_migrations(conn):
    conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY NOT NULL)'))


def get_current_version(conn) -> int:
    ensure_schema_migrations(conn)
    row = conn.execute(text('SELECT MAX(version) AS v FROM schema_migrations')).mappings().first()
    v = row['v'] if row else None
    return int(v) if v is not None else 0


def set_version(conn, version: int):
    conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'), {'v': int(version)})


def _has_column(inspector, table: str, column: str) -> bool:
    try:
        cols = [c['name'] for c in inspector.get_columns(table)]
        return column in cols
    except Exception:
        return False


def _create_table_if_missing(inspector, conn, table_name: str, ddl: str):
    if table_name in inspector.get_table_names():
        return
    conn.execute(text(ddl))


def migrate(db_engine):
    with db_engine.connect() as conn:
        current = get_current_version(conn)
        inspector = inspect(conn)

        if current < 1:
            if 'message' in inspector.get_table_names():
                if not _has_column(inspector, 'message', 'edited_at'):
                    conn.execute(text('ALTER TABLE message ADD COLUMN edited_at DATETIME'))
            set_version(conn, 1)

        if current < 2:
            if 'user' in inspector.get_table_names():
                migrations = [
                    ('failed_login_attempts', 'ALTER TABLE user ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0'),
                    ('lockout_until', 'ALTER TABLE user ADD COLUMN lockout_until DATETIME'),
                    ('last_login_at', 'ALTER TABLE user ADD COLUMN last_login_at DATETIME'),
                    ('last_login_ip', 'ALTER TABLE user ADD COLUMN last_login_ip VARCHAR(64)'),
                ]
                for col, ddl in migrations:
                    if not _has_column(inspector, 'user', col):
                        conn.execute(text(ddl))
            set_version(conn, 2)

        if current < 3:
            if 'room' in inspector.get_table_names():
                if not _has_column(inspector, 'room', 'invite_token'):
                    conn.execute(text('ALTER TABLE room ADD COLUMN invite_token VARCHAR(100)'))
            set_version(conn, 3)

        if current < 4:
            inspector = inspect(conn)
            _create_table_if_missing(
                inspector,
                conn,
                'role',
                """CREATE TABLE role (
                    id INTEGER NOT NULL PRIMARY KEY,
                    room_id INTEGER NOT NULL,
                    name VARCHAR(60) NOT NULL,
                    mention_tag VARCHAR(60) NOT NULL,
                    is_system BOOLEAN,
                    can_be_mentioned_by_everyone BOOLEAN,
                    created_at DATETIME NOT NULL
                )""",
            )
            _create_table_if_missing(
                inspector,
                conn,
                'member_role',
                """CREATE TABLE member_role (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    room_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    assigned_at DATETIME NOT NULL
                )""",
            )
            _create_table_if_missing(
                inspector,
                conn,
                'role_mention_permission',
                """CREATE TABLE role_mention_permission (
                    id INTEGER NOT NULL PRIMARY KEY,
                    room_id INTEGER NOT NULL,
                    source_role_id INTEGER NOT NULL,
                    target_role_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL
                )""",
            )
            _create_table_if_missing(
                inspector,
                conn,
                'friendship',
                """CREATE TABLE friendship (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_low_id INTEGER NOT NULL,
                    user_high_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    CONSTRAINT uq_friendship_pair UNIQUE (user_low_id, user_high_id)
                )""",
            )
            _create_table_if_missing(
                inspector,
                conn,
                'friend_request',
                """CREATE TABLE friend_request (
                    id INTEGER NOT NULL PRIMARY KEY,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    created_at DATETIME NOT NULL,
                    responded_at DATETIME
                )""",
            )
            set_version(conn, 4)

        if current < 5:
            if 'room' in inspector.get_table_names():
                if not _has_column(inspector, 'room', 'description'):
                    conn.execute(text('ALTER TABLE room ADD COLUMN description VARCHAR(500)'))
                if not _has_column(inspector, 'room', 'banner_url'):
                    conn.execute(text('ALTER TABLE room ADD COLUMN banner_url VARCHAR(300)'))
            set_version(conn, 5)

        if current < 6:
            if 'role' in inspector.get_table_names():
                if not _has_column(inspector, 'role', 'permissions_json'):
                    conn.execute(text('ALTER TABLE role ADD COLUMN permissions_json TEXT'))
            if 'channel' in inspector.get_table_names():
                if not _has_column(inspector, 'channel', 'writer_role_ids_json'):
                    conn.execute(text('ALTER TABLE channel ADD COLUMN writer_role_ids_json TEXT'))
            set_version(conn, 6)

        if current < 7:
            if 'member' in inspector.get_table_names():
                if not _has_column(inspector, 'member', 'muted_until'):
                    conn.execute(text('ALTER TABLE member ADD COLUMN muted_until DATETIME'))
            set_version(conn, 7)

        if current < 8:
            if 'room_ban' in inspector.get_table_names():
                if not _has_column(inspector, 'room_ban', 'banned_until'):
                    conn.execute(text('ALTER TABLE room_ban ADD COLUMN banned_until DATETIME'))
            set_version(conn, 8)

        conn.commit()
