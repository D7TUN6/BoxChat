**Backend Overview**

- Stack: Python 3.x, Flask, Flask-Login, Flask-SocketIO, SQLAlchemy.
- Entry: `run.py` which initializes Flask app and registers blueprints in `app/routes/*` and socket handlers in `app/sockets/events.py`.

Code layout (important files):
- `app/routes/auth.py` — login/register/session endpoints and cookie management
- `app/routes/api.py` — main REST API (channels, rooms, messages, uploads, user settings, admin)
- `app/routes/api_friends.py` — friend requests and DM creation
- `app/routes/api_search.py` — search endpoints
- `app/sockets/events.py` — Socket.IO event handlers; real-time messaging, presence, moderation commands
- `app/models/` — DB models for User, Room, Channel, Member, Message, Reaction, Role, etc.
- `app/functions/` — helper functions (uploads, role permission helpers, media checks)

Key backend responsibilities:
- Authentication: cookie/session with `flask_login`, JSON-friendly API endpoints for SPA
- Messaging: messages are created via Socket.IO `send_message` (server validates and persists) and broadcast via `receive_message` events
- Moderation: mute, kick, ban commands are implemented on server (slash commands or admin API)
- Roles & permissions: roles tied to rooms; API endpoints to create/edit/delete roles and assign to members
- Uploads: `/upload_file` and static `uploads/` serving; server validates local files and allowed external GIF hosts
- Notifications: per-user rooms (`user_<id>`) for pushing notifications and friend-request events via socketio

Security notes:
- Many endpoints expect `X-Requested-With: XMLHttpRequest` or JSON to return JSON responses.
- File URL validation allows `/uploads/` local paths and whitelisted gif hosts (e.g. giphy.com).
