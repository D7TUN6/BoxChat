**Socket.IO Events**

Client emits (examples):
- `join` { channel_id: number | null } — join channel room and personal notification room
- `send_message` { room_id, channel_id, msg, message_type?, file_url?, file_name?, file_size?, reply_to? }

Server emits (selected):
- `receive_message` — broadcast to channel when a message is created
  - payload: { id, user_id, username, avatar, msg, timestamp_iso, message_type, file_url, reactions, reply_to, mentions }
- `presence_updated` — updates user presence in channel rooms
  - payload: { user_id, username, status, last_seen_iso? }
- `message_notification` — per-user notifications pushed to `user_<id>` room
  - payload: { room_id, channel_id, message_id, from_user, snippet, unread_count, mention }
- `new_dm_message` — legacy DM notification (room_id)
- `new_dm_created` — emitted when DM is auto-created (dashboard can refresh)
- `friend_request_received`, `friend_request_updated` — friend request lifecycle events
- `member_mute_updated`, `member_removed`, `force_redirect` — moderation events
- `message_deleted`, `message_edited`, `reactions_updated`, `read_status_updated` — message lifecycle updates
- `command_result` — server response to slash commands (ok/message)

Server-side notes:
- Socket event handling and validation lives in `app/sockets/events.py`.
- `send_message` implements server-side moderation commands (slash commands) such as `/mute`, `/unmute`, `/kick`, `/ban` as well as mention parsing and allowed external media checks.

Example (client):
```js
const socket = io({ withCredentials: true });
socket.on('connect', () => socket.emit('join', { channel_id }));
socket.emit('send_message', { room_id, channel_id, msg: 'Hello' });
socket.on('receive_message', (payload) => { /* append to UI */ })
```
