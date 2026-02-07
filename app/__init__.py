"""
Flask application factory
"""
from flask import Flask
from config import UPLOAD_FOLDER, UPLOAD_SUBDIRS
import os
from app.extensions import db, socketio, login_manager


def create_app(config=None):
    """Create and configure Flask application"""
    # Get the root directory (where run.py is located)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
            MAX_CONTENT_LENGTH
        )
        flask_app.config['SECRET_KEY'] = SECRET_KEY
        flask_app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
        flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = SQLALCHEMY_TRACK_MODIFICATIONS
        flask_app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
        flask_app.config['UPLOAD_FOLDER'] = upload_dir
    
    # Initialize extensions
    db.init_app(flask_app)
    socketio.init_app(flask_app)
    login_manager.init_app(flask_app)

    # Return JSON 401 for XHR/API requests when not authenticated
    from flask import request, jsonify, redirect, url_for

    @login_manager.unauthorized_handler
    def _unauthorized():
        try:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Unauthorized'}), 401
        except Exception:
            pass
        return redirect(url_for('auth.login'))
    
    # Create upload folders
    for subdir in UPLOAD_SUBDIRS.values():
        folder_path = os.path.join(upload_dir, subdir)
        os.makedirs(folder_path, exist_ok=True)
    
    # Register blueprints
    from app.routes import auth_bp, main_bp, api_bp
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(api_bp)
    
    # Import socket handlers
    import app.sockets  # noqa
    
    # Create database tables and seed if needed
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
    """Initialize database tables"""
    from sqlalchemy import inspect, text
    from app.models import (
        User, Room, Channel, Member, Message, MessageReaction,
        ReadMessage, StickerPack, Sticker, UserMusic
    )
    
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
        try:
            if db_exists:
                print("Пробуем пересоздать базу данных...")
            db.drop_all()
            db.create_all()
            print("База данных пересоздана!")
        except Exception as e2:
            print(f"Критическая ошибка при создании БД: {e2}")
            import traceback
            traceback.print_exc()
    
    # Update schema
    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        # Update message table
        if 'message' in tables:
            columns = [col['name'] for col in inspector.get_columns('message')]
            if 'edited_at' not in columns:
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE message ADD COLUMN edited_at DATETIME'))
                        conn.commit()
                except:
                    pass
        
        # Create new tables if needed
        for table_class in [MessageReaction, ReadMessage, StickerPack, Sticker]:
            table_name = table_class.__tablename__
            if table_name not in tables:
                try:
                    table_class.__table__.create(db.engine)
                except:
                    pass
        
        # Add invite_token column if missing
        if 'room' in tables:
            columns = [col['name'] for col in inspector.get_columns('room')]
            if 'invite_token' not in columns:
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE room ADD COLUMN invite_token VARCHAR(100)'))
                        conn.commit()
                except:
                    pass
    
    except Exception as e:
        print(f"Ошибка при обновлении схемы БД: {e}")
        try:
            db.drop_all()
            db.create_all()
        except Exception as e2:
            print(f"Критическая ошибка при пересоздании БД: {e2}")


def _setup_admin_user():
    """Create admin user if it doesn't exist"""
    from app.models import User
    from werkzeug.security import generate_password_hash
    
    try:
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin', method='scrypt'),
                is_superuser=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully")
    except Exception as e:
        print(f"Ошибка при создании админа: {e}")
