"""
Socket.IO event handlers
"""
from flask_socketio import join_room, leave_room, emit
from flask_login import current_user
from app.extensions import db, socketio
from app.models import Message, Member, Room, Channel
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


@socketio.on('send_message')
def handle_send_message(data):
    """Handle incoming message"""
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
