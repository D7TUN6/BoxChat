**Architecture & Code Map**

High-level components:
- `run.py` — app boot, registers extensions, blueprints and socketio
- `app/extensions.py` — initialization of `db`, `socketio`, etc.
- `app/routes/` — blueprint-based HTTP endpoints (auth, api, spa, search, friends)
- `app/sockets/events.py` — Socket.IO handlers (real-time messaging)
- `app/models/` — SQLAlchemy models that drive domain logic (User, Room, Channel, Message, Role, etc.)
- `frontend/` — Vite + React SPA

Data flow (message send):
1. Client emits `send_message` over Socket.IO with `{ room_id, channel_id, msg, ... }`.
2. Server validates membership, permissions, bans, and file URLs.
3. Message row is created in `Message` model and flushed.
4. Server emits `receive_message` to the channel room and `message_notification` to per-user rooms.

Permissions & roles:
- Rooms have roles (`Role` model) and `MemberRole` links.
- `user_has_room_permission` (in `app/functions`) checks permission keys for operations like `manage_channels`, `mute_members`, `kick_members`, `ban_members`.

Where to add features:
- UI: `frontend/src/ui` for shared components, `frontend/src/views` for page-level logic
- Backend HTTP: `app/routes/api.py` for RESTful features
- Real-time behaviors: `app/sockets/events.py`
