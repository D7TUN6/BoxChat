# Flask application factory

from flask import Flask
from config import UPLOAD_FOLDER, UPLOAD_SUBDIRS
import os
from app.extensions import db, socketio, login_manager

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def create_app(config=None, init_db=True):
    # Create and configure Flask application
    # Get the root directory (where run.py is located)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if load_dotenv:
        try:
            load_dotenv(os.path.join(root_dir, '.env'))
        except Exception:
            pass
    template_dir = os.path.join(root_dir, 'templates')
    static_dir = os.path.join(root_dir, 'static')
    upload_dir = os.path.join(root_dir, 'uploads')
    
    flask_app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    
    # Load config
    if config:
        flask_app.config.from_object(config)
    else:
        from config import (
            SECRET_KEY, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS,
            MAX_CONTENT_LENGTH, PERMANENT_SESSION_LIFETIME, REMEMBER_COOKIE_DURATION,
            SESSION_COOKIE_NAME, SESSION_COOKIE_HTTPONLY, SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE,
            REMEMBER_COOKIE_NAME, REMEMBER_COOKIE_HTTPONLY, REMEMBER_COOKIE_SAMESITE, REMEMBER_COOKIE_SECURE
        )
        flask_app.config['SECRET_KEY'] = SECRET_KEY
        flask_app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
        flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = SQLALCHEMY_TRACK_MODIFICATIONS
        flask_app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
        flask_app.config['UPLOAD_FOLDER'] = upload_dir
        flask_app.config['PERMANENT_SESSION_LIFETIME'] = PERMANENT_SESSION_LIFETIME
        flask_app.config['REMEMBER_COOKIE_DURATION'] = REMEMBER_COOKIE_DURATION
        flask_app.config['SESSION_COOKIE_NAME'] = SESSION_COOKIE_NAME
        flask_app.config['SESSION_COOKIE_HTTPONLY'] = SESSION_COOKIE_HTTPONLY
        flask_app.config['SESSION_COOKIE_SAMESITE'] = SESSION_COOKIE_SAMESITE
        flask_app.config['SESSION_COOKIE_SECURE'] = SESSION_COOKIE_SECURE
        flask_app.config['REMEMBER_COOKIE_NAME'] = REMEMBER_COOKIE_NAME
        flask_app.config['REMEMBER_COOKIE_HTTPONLY'] = REMEMBER_COOKIE_HTTPONLY
        flask_app.config['REMEMBER_COOKIE_SAMESITE'] = REMEMBER_COOKIE_SAMESITE
        flask_app.config['REMEMBER_COOKIE_SECURE'] = REMEMBER_COOKIE_SECURE

    # Normalize sqlite path:
    # - relative sqlite path -> project root
    # - absolute sqlite path -> keep as is
    db_uri = flask_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if isinstance(db_uri, str) and db_uri.startswith('sqlite:///') and not db_uri.startswith('sqlite:////'):
        sqlite_rel = db_uri.replace('sqlite:///', '', 1)
        is_windows_abs = len(sqlite_rel) > 2 and sqlite_rel[1] == ':' and sqlite_rel[2] in ('\\', '/')
        if os.path.isabs(sqlite_rel) or is_windows_abs:
            sqlite_abs = os.path.abspath(sqlite_rel)
        else:
            sqlite_abs = os.path.abspath(os.path.join(root_dir, sqlite_rel))
        flask_app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{sqlite_abs.replace('\\', '/')}"

    flask_app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
    flask_app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
    flask_app.config.setdefault('SESSION_COOKIE_SECURE', False)
    flask_app.config.setdefault('REMEMBER_COOKIE_HTTPONLY', True)
    flask_app.config.setdefault('REMEMBER_COOKIE_SAMESITE', 'Lax')
    flask_app.config.setdefault('REMEMBER_COOKIE_SECURE', False)
    
    # Initialize extensions
    db.init_app(flask_app)
    socketio.init_app(flask_app)
    login_manager.init_app(flask_app)

    # Return JSON 401 for XHR/API requests when not authenticated
    from flask import request, jsonify, redirect, url_for

    @login_manager.unauthorized_handler
    def _unauthorized():
        try:
            if (
                request.path.startswith('/api/')
                or request.is_json
                or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            ):
                return jsonify({'error': 'Unauthorized'}), 401
        except Exception:
            pass
        return redirect(url_for('auth.login'))
    
    # Create upload folders
    for subdir in UPLOAD_SUBDIRS.values():
        folder_path = os.path.join(upload_dir, subdir)
        os.makedirs(folder_path, exist_ok=True)
    
    # Register blueprints
    from app.routes import auth_bp, main_bp, api_bp, spa_bp
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(api_bp)
    # IMPORTANT: SPA catch-all must be registered last
    flask_app.register_blueprint(spa_bp)
    
    # Import socket handlers
    import app.sockets  # noqa
    
    # Create database tables and seed if needed
    if init_db:
        with flask_app.app_context():
            _init_database(flask_app)
            _setup_admin_user()
    
    # Set up login manager
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))
    
    return flask_app

def _init_database(flask_app):
    # Initialize database tables
    from sqlalchemy import inspect, text
    from app.models import (
        User, Room, Channel, Member, Message, MessageReaction,
        ReadMessage, StickerPack, Sticker, UserMusic, AuthThrottle,
        Role, MemberRole, RoleMentionPermission, Friendship, FriendRequest
    )
    from app.functions import seed_roles_for_existing_rooms
    from app.migrations import migrate
    
    db_file = 'thecomboxmsgr.db'
    db_exists = os.path.exists(db_file)
    
    try:
        if not db_exists:
            print("База данных не найдена, создаем новую...")
        db.create_all()
        if not db_exists:
            print("База данных успешно создана!")
    except Exception as e:
        print(f"Ошибка при создании таблиц БД: {e}")
        import traceback
        traceback.print_exc()
        return

    # Update schema (migrations)
    try:
        migrate(db.engine)

        # Ensure default role system data exists for all rooms
        try:
            seed_roles_for_existing_rooms()
        except Exception:
            pass

        # Update message table
        if 'message' in inspect(db.engine).get_table_names():
            columns = [col['name'] for col in inspect(db.engine).get_columns('message')]
            if 'edited_at' not in columns:
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE message ADD COLUMN edited_at DATETIME'))
                        conn.commit()
                except:
                    pass

        # Update user table auth hardening columns
        if 'user' in inspect(db.engine).get_table_names():
            columns = [col['name'] for col in inspect(db.engine).get_columns('user')]
            user_column_migrations = [
                ('failed_login_attempts', 'ALTER TABLE user ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0'),
                ('lockout_until', 'ALTER TABLE user ADD COLUMN lockout_until DATETIME'),
                ('last_login_at', 'ALTER TABLE user ADD COLUMN last_login_at DATETIME'),
                ('last_login_ip', 'ALTER TABLE user ADD COLUMN last_login_ip VARCHAR(64)'),
            ]
            for column_name, ddl in user_column_migrations:
                if column_name not in columns:
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(text(ddl))
                            conn.commit()
                    except Exception:
                        pass
        
        # Create new tables if needed
        for table_class in [
            MessageReaction, ReadMessage, StickerPack, Sticker, AuthThrottle,
            Role, MemberRole, RoleMentionPermission,
            Friendship, FriendRequest
        ]:
            table_name = table_class.__tablename__
            if table_name not in inspect(db.engine).get_table_names():
                try:
                    table_class.__table__.create(db.engine)
                except:
                    pass
        
        # Add invite_token column if missing
        if 'room' in inspect(db.engine).get_table_names():
            columns = [col['name'] for col in inspect(db.engine).get_columns('room')]
            if 'invite_token' not in columns:
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE room ADD COLUMN invite_token VARCHAR(100)'))
                        conn.commit()
                except:
                    pass
    
    except Exception as e:
        print(f"Ошибка при обновлении схемы БД: {e}")
        import traceback
        traceback.print_exc()


def _setup_admin_user():
    # Create admin user if it doesn't exist
    from app.models import User
    from werkzeug.security import generate_password_hash
    
    try:
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('Fynjif121%', method='scrypt'),
                is_superuser=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully")
    except Exception as e:
        print(f"Ошибка при создании админа: {e}")
