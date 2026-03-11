# Flask extensions initialization
# Helps avoid circular imports by initializing extensions without app context

import os
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_login import LoginManager

db = SQLAlchemy()


def _socketio_cors_allowed_origins():
    raw = os.environ.get('BOXCHAT_SOCKETIO_CORS_ALLOWED_ORIGINS')
    if raw is None:
        # Secure default: same-origin only. Set env to '*' or a comma-separated origin list for dev.
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    if raw == '*':
        return '*'
    return [o.strip() for o in raw.split(',') if o.strip()]


socketio = SocketIO(
    async_mode='threading' if os.name == 'nt' else 'eventlet',
    cors_allowed_origins=_socketio_cors_allowed_origins(),
    ping_timeout=60,
    ping_interval=25,
    manage_transports=True,
    path='socket.io',
    engineio_logger=False,
    socketio_logger=False
)
login_manager = LoginManager()

# Configure login manager
login_manager.login_view = 'auth.login'
