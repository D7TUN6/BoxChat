"""
Flask extensions initialization
Helps avoid circular imports by initializing extensions without app context
"""
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_login import LoginManager

db = SQLAlchemy()
socketio = SocketIO(
    async_mode='threading',
    cors_allowed_origins='*',
    ping_timeout=60,
    ping_interval=25,
    manage_transports=False,
    engineio_logger=False,
    socketio_logger=False
)
login_manager = LoginManager()

# Configure login manager
login_manager.login_view = 'auth.login'
