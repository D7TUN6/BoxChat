"""
Socket.IO event handlers
"""
from flask_socketio import join_room, leave_room, emit
from flask_login import current_user
from app.extensions import db, socketio
from app.models import Message, Member, Room, Channel, ReadMessage, User
from datetime import datetime
import os


@socketio.on('join')
def on_join(data):
    """Join a channel room"""
    channel_id = data.get('channel_id')
    
    if channel_id:
        join_room(str(channel_id))
    
    # Join personal notification room
    try:
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            join_room(f"user_{current_user.id}")
    except:
        pass


@socketio.on('connect')
def on_connect():
    """Handle new socket connection: mark user online and notify rooms"""
    try:
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            # Respect user's hide_status preference
            if getattr(current_user, 'hide_status', False):
                current_user.presence_status = 'hidden'
            else:
                current_user.presence_status = 'online'
            current_user.last_seen = None
            db.session.commit()
            # Notify members in all channels of the rooms user is member of
            memberships = Member.query.filter_by(user_id=current_user.id).all()
            for m in memberships:
                # For each channel in the room, emit presence update so clients viewing channel update status
                for ch in m.room.channels:
                    socketio.emit('presence_updated', {
                        'user_id': current_user.id,
                        'username': current_user.username,
                        'status': current_user.presence_status
                    }, room=str(ch.id), skip_sid=None)  # Include sender in emission
    except Exception:
        db.session.rollback()
        pass


@socketio.on('disconnect')
def on_disconnect():
    """Mark user offline and notify rooms"""
    try:
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            # Respect hide_status: if hidden, keep hidden; otherwise set offline
            if getattr(current_user, 'hide_status', False):
                current_user.presence_status = 'hidden'
            else:
                current_user.presence_status = 'offline'
            current_user.last_seen = datetime.utcnow()
            db.session.commit()
            memberships = Member.query.filter_by(user_id=current_user.id).all()
            for m in memberships:
                for ch in m.room.channels:
                    socketio.emit('presence_updated', {
                        'user_id': current_user.id,
                        'username': current_user.username,
                        'status': current_user.presence_status,
                        'last_seen_iso': current_user.last_seen.strftime('%Y-%m-%dT%H:%M:%SZ') if current_user.last_seen else None
                    }, room=str(ch.id), skip_sid=None)  # Include sender in emission
    except Exception:
        db.session.rollback()
        pass


@socketio.on('send_message')
def handle_send_message(data):
    """Handle incoming message"""
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

    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    if not member:
        emit('error', {'message': 'Нет доступа'})
        return
    
    can_post = True
    if room.type == 'broadcast' and member.role not in ['owner', 'admin']:
        can_post = False
    
    if not can_post:
        emit('error', {'message': 'Только владельцы и администраторы могут публиковать'})
        return
    
    # Validate file_url if provided: only allow files from '/uploads/' that exist on disk
    if file_url:
        try:
            # only accept relative uploads path
            if not file_url.startswith('/uploads/'):
                file_url = None
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                abs_path = os.path.join(base_dir, file_url.lstrip('/'))
                if not os.path.exists(abs_path):
                    file_url = None
        except Exception:
            file_url = None

    # If file_url was validated, derive server-side filename and size to avoid spoofing
    if file_url:
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
        'reply_to': reply_payload
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
                'unread_count': unread_count
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