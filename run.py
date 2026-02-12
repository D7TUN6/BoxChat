# Entry point for the BoxChat application

from app import create_app
from app.extensions import socketio

app = create_app(init_db=False)

if __name__ == '__main__':
    print("[SERVER STARTUP] Starting BoxChat...")
    print("[SERVER CONFIG] Socket.IO running on port 5000")
    try:
        socketio.run(
            app,
            host='127.0.0.1',
            port=5000,
            allow_unsafe_werkzeug=True,
            debug=False,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        print("\n[SERVER SHUTDOWN] Ctrl+C received, shutting down...")

