# Socket.IO event handlers

from flask_socketio import join_room, leave_room, emit
from flask_login import current_user
from app.extensions import db, socketio
from app.models import Message, Member, Room, Channel, ReadMessage, User, Role, MemberRole, RoomBan
from app.functions import can_user_mention_role
from datetime import datetime, timedelta
import json
import os
import re
from urllib.parse import urlparse
from app.functions import get_user_role_ids, user_has_room_permission
from sqlalchemy import func


def _parse_mentions(content, room_id):
    # Parse @username + @role mentions (including @everyone role)
    text = content or ''
    tokens = re.findall(r'@([a-zA-Z0-9_-]{2,60})', text)
    if not tokens:
        return {
            'mention_everyone': False,
            'mentioned_user_ids': [],
            'mentioned_usernames': [],
            'mentioned_role_ids': [],
            'mentioned_role_tags': [],
            'denied_role_tags': [],
        }

    members = Member.query.filter_by(room_id=room_id).all()
    username_to_user = {}
    for m in members:
        if m.user:
            username_to_user[m.user.username.lower()] = m.user

    room_roles = Role.query.filter_by(room_id=room_id).all()
    role_tag_to_role = {r.mention_tag.lower(): r for r in room_roles}

    username_tokens = set()
    role_tokens = set()
    for token in tokens:
        low = token.lower()
        if low in role_tag_to_role:
            role_tokens.add(low)
        else:
            username_tokens.add(low)

    mentioned_users = []
    for uname in sorted(username_tokens):
        user = username_to_user.get(uname)
        if user:
            mentioned_users.append(user)

    allowed_roles = []
    denied_role_tags = []
    for tag in sorted(role_tokens):
        role = role_tag_to_role[tag]
        if can_user_mention_role(current_user.id, room_id, role):
            allowed_roles.append(role)
        else:
            denied_role_tags.append(role.mention_tag)

    role_user_ids = set()
    for role in allowed_roles:
        links = MemberRole.query.filter_by(room_id=room_id, role_id=role.id).all()
        for link in links:
            role_user_ids.add(link.user_id)

    all_mentioned_user_ids = set([u.id for u in mentioned_users]) | role_user_ids
    all_mentioned_usernames = []
    for uid in sorted(all_mentioned_user_ids):
        user = User.query.get(uid)
        if user:
            all_mentioned_usernames.append(user.username)

    mention_everyone = any(r.mention_tag.lower() == 'everyone' for r in allowed_roles)
    return {
        'mention_everyone': mention_everyone,
        'mentioned_user_ids': sorted(all_mentioned_user_ids),
        'mentioned_usernames': all_mentioned_usernames,
        'mentioned_role_ids': [r.id for r in allowed_roles],
        'mentioned_role_tags': [r.mention_tag for r in allowed_roles],
        'denied_role_tags': denied_role_tags,
    }


def _is_allowed_external_media_url(url):
    try:
        parsed = urlparse(str(url or '').strip())
        if parsed.scheme not in ('http', 'https'):
            return False
        host = (parsed.netloc or '').lower()
        if not host:
            return False
        allowed_hosts = (
            'giphy.com',
            'giphyusercontent.com',
        )
        return any(host == h or host.endswith(f'.{h}') for h in allowed_hosts)
    except Exception:
        return False


def _parse_duration_to_minutes(token: str):
    raw = str(token or '').strip().lower()
    if not raw:
        return None
    m = re.match(r'^(\d+)([mhd]?)$', raw)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2) or 'm'
    if value <= 0:
        return None
    if unit == 'm':
        return value
    if unit == 'h':
        return value * 60
    if unit == 'd':
        return value * 60 * 24
    return None


def _find_room_member_by_token(room_id: int, token: str):
    username = str(token or '').strip()
    if username.startswith('@'):
        username = username[1:]
    if not username:
        return None
    return Member.query.join(User, Member.user_id == User.id).filter(
        Member.room_id == int(room_id),
        func.lower(User.username) == username.lower(),
    ).first()


def _emit_command_result(ok: bool, message: str):
    emit('command_result', {'ok': bool(ok), 'message': str(message or '')})

@socketio.on('join')
def on_join(data):
    # Join a channel room
    channel_id = data.get('channel_id')
    
    if channel_id:
        join_room(str(channel_id))
        if hasattr(current_user, 'id'):
            print(f"[SOCKET JOIN] User {current_user.id} joined channel room: {channel_id}")
    
    # Join personal notification room
    try:
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            room_name = f"user_{current_user.id}"
            join_room(room_name)
            print(f"[SOCKET JOIN] User {current_user.id} joined notification room: {room_name}")
    except Exception as e:
        print(f"[SOCKET JOIN ERROR] Failed to join notification room: {e}")
        pass

@socketio.on('connect')
def on_connect():
    # Handle new socket connection: mark user online and notify rooms
    print(f"[SOCKET CONNECT] Connection event received")
    try:
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            user_id = current_user.id
            room_name = f"user_{user_id}"
            print(f"[SOCKET CONNECT] User {user_id} ({current_user.username}) is authenticated")
            
            # Join user's personal notification room immediately
            try:
                join_room(room_name)
                print(f"[SOCKET CONNECT] ✓ User {user_id} joined notification room: {room_name}")
            except Exception as e:
                print(f"[SOCKET CONNECT] ✗ Failed to join notification room: {e}")
                raise
            
            # Respect user's hide_status preference
            if getattr(current_user, 'hide_status', False):
                current_user.presence_status = 'hidden'
            else:
                current_user.presence_status = 'online'
            current_user.last_seen = None
            db.session.commit()
            print(f"[SOCKET CONNECT] ✓ User {user_id} status set to online")
            
            # Notify members in all channels of the rooms user is member of
            memberships = Member.query.filter_by(user_id=user_id).all()
            print(f"[SOCKET CONNECT] User {user_id} has {len(memberships)} memberships")
            
            for m in memberships:
                # For each channel in the room, emit presence update so clients viewing channel update status
                for ch in m.room.channels:
                    try:
                        socketio.emit('presence_updated', {
                            'user_id': current_user.id,
                            'username': current_user.username,
                            'status': current_user.presence_status
                        }, room=str(ch.id), skip_sid=None)  # Include sender in emission
                    except Exception as e:
                        print(f"[SOCKET CONNECT] Error emitting presence for channel {ch.id}: {e}")
            
            print(f"[SOCKET CONNECT] ✓ User {user_id} fully connected")
        else:
            print(f"[SOCKET CONNECT] No authenticated user found")
    except Exception as e:
        print(f"[SOCKET CONNECT] ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        pass


@socketio.on('disconnect')
def on_disconnect():
    # Mark user offline and notify rooms
    user_id = None
    try:
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            user_id = current_user.id
            print(f"[SOCKET DISCONNECT] User {user_id} disconnecting...")
            # Respect hide_status: if hidden, keep hidden; otherwise set offline
            if getattr(current_user, 'hide_status', False):
                current_user.presence_status = 'hidden'
            else:
                current_user.presence_status = 'offline'
            current_user.last_seen = datetime.utcnow()
            db.session.commit()
            print(f"[SOCKET DISCONNECT] User {user_id} status set to offline, notifying rooms...")
            memberships = Member.query.filter_by(user_id=user_id).all()
            for m in memberships:
                for ch in m.room.channels:
                    socketio.emit('presence_updated', {
                        'user_id': current_user.id,
                        'username': current_user.username,
                        'status': current_user.presence_status,
                        'last_seen_iso': current_user.last_seen.strftime('%Y-%m-%dT%H:%M:%SZ') if current_user.last_seen else None
                    }, room=str(ch.id), skip_sid=None)  # Include sender in emission
            print(f"[SOCKET DISCONNECT] User {user_id} disconnect complete")
    except Exception as e:
        print(f"[SOCKET DISCONNECT ERROR] {e}")
        if user_id:
            print(f"[SOCKET DISCONNECT ERROR] Error for user {user_id}")
        db.session.rollback()
        pass


@socketio.on('send_message')
def handle_send_message(data):
    # Handle incoming message
    import sys
    print(f"[handle_send_message] START - from user {current_user.id} ({current_user.username})", file=sys.stderr)
    
    channel_id = data.get('channel_id')
    content = data.get('msg', '')
    room_id = data.get('room_id')
    message_type = data.get('message_type', 'text')
    file_url = data.get('file_url')
    file_name = data.get('file_name')
    file_size = data.get('file_size')
    reply_to = data.get('reply_to')
    
    # Normalize content: strip whitespace but preserve internal line breaks
    if content and isinstance(content, str):
        content = content.strip()
        lines = content.split('\n')
        # Remove empty lines at start and end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        # Remove leading spaces but preserve line breaks
        content = '\n'.join(line.lstrip() for line in lines)
    
    # Normalize ids to ints when possible
    try:
        if channel_id is not None:
            channel_id = int(channel_id)
    except Exception:
        pass
    try:
        if room_id is not None:
            room_id = int(room_id)
    except Exception:
        pass

    # Validate room and channel exist
    room = Room.query.get(room_id)
    if not room:
        emit('error', {'message': 'Комната не найдена'})
        return

    channel = Channel.query.get(channel_id)
    if not channel or channel.room_id != room_id:
        emit('error', {'message': 'Канал не найден'})
        return

    memberships = Member.query.filter_by(user_id=current_user.id, room_id=room_id).all()
    member = memberships[0] if memberships else None

    if not memberships:
        emit('error', {'message': 'Нет доступа'})
        return

    # Active room ban check (supports temporary bans).
    active_ban = RoomBan.query.filter_by(room_id=room_id, user_id=current_user.id).first()
    if active_ban:
        banned_until = getattr(active_ban, 'banned_until', None)
        if banned_until and banned_until <= datetime.utcnow():
            try:
                db.session.delete(active_ban)
                db.session.commit()
            except Exception:
                db.session.rollback()
        else:
            _emit_command_result(False, 'You are banned from this room.')
            emit('error', {'message': 'Вы забанены в этой комнате'})
            return

    # Slash moderation commands:
    # /mute @user 60m reason
    # /unmute @user
    # /kick @user reason
    # /ban @user 2h reason  (duration currently informational for ban)
    if message_type == 'text' and not file_url and isinstance(content, str) and content.startswith('/'):
        parts = content.split()
        cmd = (parts[0].lower() if parts else '')
        if cmd in {'/mute', '/unmute', '/kick', '/ban'}:
            def _can(permission_key: str) -> bool:
                return bool(getattr(current_user, 'is_superuser', False) or user_has_room_permission(current_user.id, room_id, permission_key))

            if cmd == '/mute':
                if not _can('mute_members'):
                    _emit_command_result(False, 'No permission to mute members.')
                    return
                if len(parts) < 3:
                    _emit_command_result(False, 'Usage: /mute @username <duration[m|h|d]> [reason]')
                    return
                target = _find_room_member_by_token(room_id, parts[1])
                minutes = _parse_duration_to_minutes(parts[2])
                if not target:
                    _emit_command_result(False, 'User not found in this room.')
                    return
                if minutes is None:
                    _emit_command_result(False, 'Invalid duration. Example: 30m, 2h, 1d')
                    return
                if target.user_id == current_user.id:
                    _emit_command_result(False, 'You cannot mute yourself.')
                    return
                if target.role == 'owner' and not getattr(current_user, 'is_superuser', False):
                    _emit_command_result(False, 'Cannot mute room owner.')
                    return
                until = datetime.utcnow() + timedelta(minutes=minutes)
                targets = Member.query.filter_by(user_id=target.user_id, room_id=room_id).all()
                for t in targets:
                    t.muted_until = until
                db.session.commit()
                socketio.emit('member_mute_updated', {
                    'room_id': room_id,
                    'user_id': target.user_id,
                    'muted_until': until.strftime('%Y-%m-%dT%H:%M:%SZ'),
                }, room=str(room_id))
                _emit_command_result(True, f'{target.user.username} muted for {minutes}m.')
                return

            if cmd == '/unmute':
                if not _can('mute_members'):
                    _emit_command_result(False, 'No permission to unmute members.')
                    return
                if len(parts) < 2:
                    _emit_command_result(False, 'Usage: /unmute @username')
                    return
                target = _find_room_member_by_token(room_id, parts[1])
                if not target:
                    _emit_command_result(False, 'User not found in this room.')
                    return
                targets = Member.query.filter_by(user_id=target.user_id, room_id=room_id).all()
                for t in targets:
                    t.muted_until = None
                db.session.commit()
                socketio.emit('member_mute_updated', {
                    'room_id': room_id,
                    'user_id': target.user_id,
                    'muted_until': None,
                }, room=str(room_id))
                _emit_command_result(True, f'{target.user.username} unmuted.')
                return

            if cmd == '/kick':
                if not _can('kick_members'):
                    _emit_command_result(False, 'No permission to kick members.')
                    return
                if len(parts) < 2:
                    _emit_command_result(False, 'Usage: /kick @username [reason]')
                    return
                target = _find_room_member_by_token(room_id, parts[1])
                if not target:
                    _emit_command_result(False, 'User not found in this room.')
                    return
                if target.user_id == current_user.id:
                    _emit_command_result(False, 'You cannot kick yourself.')
                    return
                if target.role == 'owner' and not getattr(current_user, 'is_superuser', False):
                    _emit_command_result(False, 'Cannot kick room owner.')
                    return
                targets = Member.query.filter_by(user_id=target.user_id, room_id=room_id).all()
                for t in targets:
                    db.session.delete(t)
                db.session.commit()
                socketio.emit('member_removed', {'user_id': target.user_id, 'room_id': room_id}, room=str(room_id))
                socketio.emit('force_redirect', {'location': '/', 'reason': 'You were kicked from this room.'}, room=f"user_{target.user_id}")
                _emit_command_result(True, f'{target.user.username} kicked.')
                return

            if cmd == '/ban':
                if not _can('ban_members'):
                    _emit_command_result(False, 'No permission to ban members.')
                    return
                if len(parts) < 2:
                    _emit_command_result(False, 'Usage: /ban @username [duration] [reason]')
                    return
                target = _find_room_member_by_token(room_id, parts[1])
                if not target:
                    _emit_command_result(False, 'User not found in this room.')
                    return
                if target.user_id == current_user.id:
                    _emit_command_result(False, 'You cannot ban yourself.')
                    return
                if target.role == 'owner' and not getattr(current_user, 'is_superuser', False):
                    _emit_command_result(False, 'Cannot ban room owner.')
                    return
                duration_token = parts[2] if len(parts) >= 3 else ''
                duration_minutes = _parse_duration_to_minutes(duration_token)
                reason_start = 3 if duration_minutes is not None else 2
                reason = ' '.join(parts[reason_start:]).strip() or 'Banned by moderator'
                banned_until = datetime.utcnow() + timedelta(minutes=duration_minutes) if duration_minutes else None
                existing_ban = RoomBan.query.filter_by(room_id=room_id, user_id=target.user_id).first()
                if not existing_ban:
                    db.session.add(RoomBan(
                        room_id=room_id,
                        user_id=target.user_id,
                        banned_by_id=current_user.id,
                        reason=reason,
                        banned_until=banned_until,
                        messages_deleted=False,
                    ))
                else:
                    existing_ban.reason = reason
                    existing_ban.banned_by_id = current_user.id
                    existing_ban.banned_until = banned_until
                targets = Member.query.filter_by(user_id=target.user_id, room_id=room_id).all()
                for t in targets:
                    db.session.delete(t)
                db.session.commit()
                socketio.emit('member_removed', {'user_id': target.user_id, 'room_id': room_id}, room=str(room_id))
                socketio.emit('force_redirect', {'location': '/', 'reason': f'You were banned. Reason: {reason}'}, room=f"user_{target.user_id}")
                if banned_until is not None:
                    _emit_command_result(True, f'{target.user.username} banned until {banned_until.strftime("%Y-%m-%d %H:%M UTC")}.')
                else:
                    _emit_command_result(True, f'{target.user.username} banned.')
                return
    
    can_post = True
    roles = {str(getattr(m, 'role', 'member') or 'member') for m in memberships}
    is_room_admin = bool('owner' in roles or 'admin' in roles)
    if room.type == 'broadcast' and not is_room_admin:
        can_post = False
    now_utc = datetime.utcnow()
    if any(getattr(m, 'muted_until', None) and m.muted_until > now_utc for m in memberships):
        can_post = False

    # Channel-level write restrictions: only selected roles can post.
    try:
        writer_role_ids = json.loads(channel.writer_role_ids_json or '[]') if getattr(channel, 'writer_role_ids_json', None) else []
    except Exception:
        writer_role_ids = []
    if writer_role_ids:
        user_roles = get_user_role_ids(current_user.id, room_id)
        has_whitelisted_role = any(int(rid) in user_roles for rid in writer_role_ids)
        if not has_whitelisted_role and not is_room_admin:
            can_post = False

    if not can_post:
        emit('error', {'message': 'Только владельцы и администраторы могут публиковать'})
        return
    
    # Validate file_url if provided:
    # - allow local uploads (/uploads/...) if file exists
    # - allow trusted external gif hosts for GIF picker
    if file_url:
        try:
            if file_url.startswith('/uploads/'):
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                abs_path = os.path.join(base_dir, file_url.lstrip('/'))
                if not os.path.exists(abs_path):
                    file_url = None
            elif not _is_allowed_external_media_url(file_url):
                file_url = None
        except Exception:
            file_url = None

    # If local upload URL was validated, derive server-side filename and size to avoid spoofing
    if file_url and str(file_url).startswith('/uploads/'):
        try:
            file_name = os.path.basename(file_url)
        except Exception:
            pass
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            abs_path = os.path.join(base_dir, file_url.lstrip('/'))
            try:
                file_size = os.path.getsize(abs_path)
            except Exception:
                pass
        except Exception:
            pass

    # Create and save message
    msg = Message(
        content=content,
        user_id=current_user.id,
        channel_id=channel_id,
        message_type=message_type,
        file_url=file_url,
        file_name=file_name,
        file_size=file_size,
        reply_to_id=(reply_to.get('id') if isinstance(reply_to, dict) and reply_to.get('id') else None)
    )
    db.session.add(msg)
    db.session.commit()

    mention_data = _parse_mentions(content, room_id)
    
    # Load reactions for the message
    reactions_data = {}
    for reaction in msg.reactions:
        if reaction.emoji not in reactions_data:
            reactions_data[reaction.emoji] = []
        reactions_data[reaction.emoji].append(reaction.user.username)
    
    # Build reply metadata from saved message reference if available
    reply_payload = None
    try:
        if getattr(msg, 'reply_to_id', None):
            orig = Message.query.get(msg.reply_to_id)
            if orig:
                snippet = (orig.content or '').split('\n')[0][:200]
                reply_payload = {
                    'id': orig.id,
                    'username': orig.user.username if orig.user else 'Unknown',
                    'snippet': snippet
                }
    except Exception:
        reply_payload = (reply_to if reply_to else None)

    # Broadcast to channel (include server-built reply metadata)
    print(f"[handle_send_message] Broadcasting receive_message to channel {channel_id}", file=sys.stderr)
    emit('receive_message', {
        'id': msg.id,
        'user_id': current_user.id,
        'username': current_user.username,
        'avatar': current_user.avatar_url,
        'msg': content,
        'timestamp_iso': msg.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'message_type': message_type,
        'file_url': file_url,
        'file_name': file_name,
        'file_size': file_size,
        'edited_at_iso': msg.edited_at.strftime('%Y-%m-%dT%H:%M:%SZ') if msg.edited_at else None,
        'reactions': reactions_data,
        'reply_to': reply_payload,
        'mentions': {
            'everyone': mention_data['mention_everyone'],
            'user_ids': mention_data['mentioned_user_ids'],
            'usernames': mention_data['mentioned_usernames'],
            'role_ids': mention_data['mentioned_role_ids'],
            'role_tags': mention_data['mentioned_role_tags'],
            'denied_role_tags': mention_data['denied_role_tags'],
        }
    }, room=str(channel_id))

    # Send per-user notifications and unread counts to members' personal rooms
    try:
        members = Member.query.filter_by(room_id=room_id).all()
        print(f"[handle_send_message] Sending notifications to {len(members)} members", file=sys.stderr)
        for m in members:
            uid = m.user_id
            # skip sender
            if uid == current_user.id:
                continue

            # compute unread count for this user in this channel
            # Count all messages after last_read_message_id, excluding the current user's own messages
            unread_count = 0
            rm = ReadMessage.query.filter_by(user_id=uid, channel_id=channel_id).first()
            if rm and rm.last_read_message_id:
                # Messages after what they've read
                unread_count = Message.query.filter(
                    Message.channel_id == channel_id,
                    Message.id > rm.last_read_message_id
                ).count()
            else:
                # No reading history, count all messages
                unread_count = Message.query.filter(
                    Message.channel_id == channel_id
                ).count()

            # Build small snippet for notification
            snippet = (content or '')
            if snippet:
                snippet = snippet.strip().split('\n')[0][:140]

            payload = {
                'room_id': room_id,
                'channel_id': channel_id,
                'message_id': msg.id,
                'from_user': current_user.username,
                'from_user_id': current_user.id,
                'snippet': snippet,
                'unread_count': unread_count,
                'mention': (
                    mention_data['mention_everyone']
                    or uid in set(mention_data['mentioned_user_ids'])
                ),
                'mention_everyone': mention_data['mention_everyone'],
                'mention_roles': mention_data['mentioned_role_tags'],
            }

            # Emit a generic notification event to the user's personal room
            print(f"[handle_send_message] Sending notification to user {uid}: {payload}", file=sys.stderr)
            socketio.emit('message_notification', payload, room=f"user_{uid}")

            # For DM rooms, keep the legacy dashboard handler name
            try:
                if room.type == 'dm':
                    socketio.emit('new_dm_message', {'room_id': room.id}, room=f"user_{uid}")
            except Exception:
                pass
    except Exception:
        db.session.rollback()
        pass
    
    print(f"[handle_send_message] COMPLETE", file=sys.stderr)
