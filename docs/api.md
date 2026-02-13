**API Reference (selected endpoints)**

Authentication
- `POST /api/v1/auth/login` — JSON or form login. Returns user and redirect on success.
- `POST /api/v1/auth/register` — create account and login.
- `GET /api/v1/auth/session` — returns `{ authenticated: true/false, user: {...} }` used by frontend router loader.

User
- `GET /api/v1/user/me` — current user summary
- `GET /api/v1/user/<id>/profile` — profile data
- `POST /api/v1/user/avatar` — upload avatar (form)

Rooms & Channels
- `GET /api/v1/rooms` — list rooms visible to user
- `GET /api/v1/room/<room_id>/members` — members list
- `GET /api/v1/room/<room_id>/roles` — roles in room
- `POST /room/<room_id>/add_channel` — add a channel (form POST)
- `PATCH /api/v1/room/<room_id>/channel/<channel_id>/permissions` — change channel permissions
- `POST /api/v1/room/<room_id>/join` — join a room

Messages
- `GET /api/v1/channel/<channel_id>/messages?limit=&offset=` — list messages (used by RoomPage)
- `POST /message/<message_id>/reaction` — toggle reaction (body: { emoji, reaction_type })
- `POST /message/<message_id>/delete` — delete message
- `POST /message/<message_id>/edit` — edit message
- `POST /message/<message_id>/forward` — forward message to another channel/room
- `POST /channel/<channel_id>/mark_read` — mark channel read

Reactions & GIFs
- `GET /api/v1/reactions` — server-configured allowed reactions
- `GET /api/v1/gifs/trending` and `/api/v1/gifs/search?q=` — proxy to Giphy (requires GIPHY_API_KEY env var)

Friends & DMs
- `POST /api/v1/friends/request` — send friend request (body: { username })
- `GET /api/v1/friends/requests` — list incoming/outgoing
- `POST /api/v1/friends/requests/<id>/respond` — accept/decline
- `POST /api/v1/dm/<user_id>/create` — create DM room (friends only)

Uploads & Files
- `POST /upload_file` — upload file to server `uploads/` folder
- `GET /uploads/<path:filename>` — serve uploaded file

Admin
- Several admin endpoints exist for banning, muting, promoting users — see `app/routes/api.py` under `/admin/` paths.

Notes:
- Many endpoints expect `X-Requested-With: XMLHttpRequest` and return JSON when requested via fetch.
- Prefer using the Socket.IO channel operations for real-time send/receive of messages; REST is used for history and mutations.
