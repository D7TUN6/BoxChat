"""
API routes (uploads, settings, channel management, message actions)
"""
import os
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, send_from_directory, current_app
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash
from datetime import datetime
from app.extensions import db, socketio
from app.models import (
    User, Room, Channel, Member, Message, UserMusic,
    MessageReaction, ReadMessage
)
from app.functions import save_uploaded_file, resize_image, is_image_file, is_music_file, is_video_file

api_bp = Blueprint('api', __name__)


# Helper functions
def get_role(user_id, room_id):
    """Get user role in room"""
    member = Member.query.filter_by(user_id=user_id, room_id=room_id).first()
    return member.role if member else None


def save_file(file, subfolder='files'):
    """Wrapper for save_uploaded_file that uses current_app's upload folder"""
    return save_uploaded_file(file, subfolder, current_app.config['UPLOAD_FOLDER'])


def get_upload_folder():
    """Get upload folder from current app config"""
    return current_app.config.get('UPLOAD_FOLDER', 'uploads')


# --- CHANNEL MANAGEMENT ---

@api_bp.route('/room/<int:room_id>/add_channel', methods=['POST'])
@login_required
def add_channel(room_id):
    """Add channel to room"""
    role = get_role(current_user.id, room_id)
    if role not in ['owner', 'admin']:
        return jsonify({'error': 'Нет доступа'}), 403
    
    name = request.form.get('name')
    c = Channel(name=name, room_id=room_id)
    db.session.add(c)
    db.session.commit()
    
    return redirect(url_for('main.view_room', room_id=room_id))


@api_bp.route('/room/<int:room_id>/channel/<int:channel_id>/edit', methods=['POST'])
@login_required
def edit_channel(room_id, channel_id):
    """Edit channel"""
    role = get_role(current_user.id, room_id)
    if role not in ['owner', 'admin']:
        return jsonify({'error': 'Нет доступа'}), 403
    
    channel = Channel.query.get_or_404(channel_id)
    if channel.room_id != room_id:
        return jsonify({'error': 'Неверный канал'}), 400
    
    channel.name = request.form.get('name', channel.name)
    channel.description = request.form.get('description', channel.description)
    channel.icon_emoji = request.form.get('icon_emoji', channel.icon_emoji)
    
    if 'icon_file' in request.files:
        file = request.files['icon_file']
        if file and file.filename:
            filepath = save_file(file, 'channel_icons')
            if filepath:
                # Resize to 32x32
                full_path = os.path.join(get_upload_folder(), 'channel_icons', filepath.split('/')[-1])
                resize_image(full_path, (32, 32))
                channel.icon_image_url = filepath
    
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/room/<int:room_id>/channel/<int:channel_id>/delete', methods=['POST'])
@login_required
def delete_channel(room_id, channel_id):
    """Delete channel"""
    role = get_role(current_user.id, room_id)
    if role not in ['owner', 'admin']:
        return jsonify({'error': 'Нет доступа'}), 403
    
    channel = Channel.query.get_or_404(channel_id)
    if channel.room_id != room_id:
        return jsonify({'error': 'Неверный канал'}), 400
    
    db.session.delete(channel)
    db.session.commit()
    return jsonify({'success': True})


# --- USER SETTINGS ---

@api_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User settings page"""
    if request.method == 'POST':
        current_user.bio = request.form.get('bio')
        current_user.privacy_searchable = 'privacy_searchable' in request.form
        current_user.privacy_listable = 'privacy_listable' in request.form
        # Presence hiding
        if 'hide_status' in request.form:
            current_user.hide_status = True
            current_user.presence_status = 'hidden'
        else:
            current_user.hide_status = False
            # Set to online if not hidden
            if current_user.presence_status != 'away':
                current_user.presence_status = 'online'
        
        if 'avatar_file' in request.files:
            file = request.files['avatar_file']
            if file and file.filename:
                filepath = save_file(file, 'avatars')
                if filepath:
                    current_user.avatar_url = filepath
        
        db.session.commit()
        
        # Notify all members of status change
        from app.models import Member
        memberships = Member.query.filter_by(user_id=current_user.id).all()
        for m in memberships:
            for ch in m.room.channels:
                socketio.emit('presence_updated', {
                    'user_id': current_user.id,
                    'username': current_user.username,
                    'status': current_user.presence_status
                }, room=str(ch.id), skip_sid=None)
        
        flash('Настройки обновлены')
    
    return render_template('settings.html', user=current_user)


@api_bp.route('/user/avatar/delete', methods=['POST'])
@login_required
def delete_user_avatar():
    """Delete user avatar"""
    if current_user.avatar_url and current_user.avatar_url != "https://via.placeholder.com/50":
        if current_user.avatar_url.startswith('/uploads/'):
            try:
                filename = current_user.avatar_url.lstrip('/uploads/').lstrip('/')
                abs_path = os.path.join(get_upload_folder(), filename)
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except:
                pass
        
        current_user.avatar_url = "https://via.placeholder.com/50"
        db.session.commit()
    
    return jsonify({'success': True})


@api_bp.route('/user/delete', methods=['POST'])
@login_required
def delete_user_account():
    """Delete user account and all associated data"""
    data = request.json
    password = data.get('password')
    
    if not password:
        return jsonify({'error': 'Не указан пароль'}), 400
    
    if not check_password_hash(current_user.password, password):
        return jsonify({'error': 'Неверный пароль'}), 403
    
    user_id = current_user.id
    
    try:
        # Delete user's music
        UserMusic.query.filter_by(user_id=user_id).delete()
        
        # Delete reactions
        MessageReaction.query.filter_by(user_id=user_id).delete()
        
        # Delete read messages
        ReadMessage.query.filter_by(user_id=user_id).delete()
        
        # Delete memberships
        Member.query.filter_by(user_id=user_id).delete()
        
        # Delete messages
        Message.query.filter_by(user_id=user_id).delete()
        
        # Delete avatar file
        if current_user.avatar_url and current_user.avatar_url.startswith('/uploads/'):
            try:
                filename = current_user.avatar_url.lstrip('/uploads/').lstrip('/')
                abs_path = os.path.join(get_upload_folder(), filename)
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except:
                pass
        
        # Delete account
        from flask_login import logout_user
        logout_user()
        db.session.delete(current_user)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при удалении аккаунта: {str(e)}'}), 500


# --- ROOM SETTINGS ---

@api_bp.route('/room/<int:room_id>/settings', methods=['GET', 'POST'])
@login_required
def room_settings(room_id):
    """Room settings page"""
    room = Room.query.get_or_404(room_id)
    role = get_role(current_user.id, room_id)
    
    if role not in ['owner', 'admin']:
        flash('Нет доступа')
        return redirect(url_for('main.view_room', room_id=room_id))
    
    if request.method == 'POST':
        room.name = request.form.get('name', room.name)
        
        if 'avatar_file' in request.files:
            file = request.files['avatar_file']
            if file and file.filename:
                filepath = save_file(file, 'room_avatars')
                if filepath:
                    room.avatar_url = filepath
        
        db.session.commit()
        flash('Настройки комнаты обновлены')
        return redirect(url_for('main.view_room', room_id=room_id))
    
    return render_template('room_settings.html', room=room)


@api_bp.route('/channel/<int:channel_id>/mark_read', methods=['POST'])
@login_required
def mark_channel_read(channel_id):
    """Mark channel as read for current user (set last_read to last message)"""
    from app.models import Channel, Message, ReadMessage
    ch = Channel.query.get_or_404(channel_id)
    last_msg = Message.query.filter_by(channel_id=channel_id).order_by(Message.id.desc()).first()
    if not last_msg:
        return jsonify({'success': True, 'message': 'no_messages'})

    rm = ReadMessage.query.filter_by(user_id=current_user.id, channel_id=channel_id).first()
    if rm:
        rm.last_read_message_id = last_msg.id
        rm.last_read_at = datetime.utcnow()
    else:
        rm = ReadMessage(user_id=current_user.id, channel_id=channel_id, last_read_message_id=last_msg.id)
        db.session.add(rm)
    db.session.commit()

    # notify others in channel about read status
    socketio.emit('read_status_updated', {
        'user_id': current_user.id,
        'username': current_user.username,
        'channel_id': channel_id
    }, room=str(channel_id))

    return jsonify({'success': True})


@api_bp.route('/room/<int:room_id>/avatar/delete', methods=['POST'])
@login_required
def delete_room_avatar(room_id):
    """Delete room avatar"""
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    if not member or member.role not in ['owner', 'admin']:
        return jsonify({'error': 'Нет прав'}), 403
    
    if room.avatar_url:
        if room.avatar_url.startswith('/uploads/'):
            try:
                filename = room.avatar_url.lstrip('/uploads/').lstrip('/')
                abs_path = os.path.join(get_upload_folder(), filename)
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except:
                pass

        room.avatar_url = None
        db.session.commit()
    
    return jsonify({'success': True})


# --- FILE UPLOADS ---

@api_bp.route('/upload_file', methods=['POST'])
@login_required
def upload_file():
    """Upload file (image, music, or document)"""
    if 'file' not in request.files:
        return jsonify({'error': 'Нет файла'}), 400
    
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'error': 'Файл не выбран'}), 400
    # Save according to type with validation
    if is_image_file(file.filename):
        filepath = save_file(file, 'files')
        filetype = 'image'
    elif is_music_file(file.filename):
        filepath = save_file(file, 'music')
        filetype = 'music'
    elif is_video_file(file.filename):
        filepath = save_file(file, 'videos')
        filetype = 'video'
    else:
        filepath = save_file(file, 'files')
        filetype = 'file'

    if not filepath:
        return jsonify({'error': 'Ошибка сохранения файла'}), 500

    # Ensure filename is returned (basename of saved path)
    try:
        filename = os.path.basename(filepath)
    except Exception:
        filename = file.filename

    return jsonify({'success': True, 'url': filepath, 'type': filetype, 'filename': filename})


@api_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded file"""
    return send_from_directory(get_upload_folder(), filename)


@api_bp.route('/music/add', methods=['POST'])
@login_required
def add_music():
    """Add music to user library"""
    if 'music_file' not in request.files:
        return jsonify({'error': 'Нет файла'}), 400
    
    file = request.files['music_file']
    if not file or not file.filename or not is_music_file(file.filename):
        return jsonify({'error': 'Неверный формат музыки'}), 400
    
    filepath = save_file(file, 'music')
    if not filepath:
        return jsonify({'error': 'Ошибка загрузки'}), 500
    
    title = request.form.get('title', 'Без названия')
    artist = request.form.get('artist', 'Неизвестный исполнитель')
    
    cover_url = None
    if 'cover_file' in request.files:
        cover_file = request.files['cover_file']
        if cover_file and cover_file.filename:
            cover_url = save_file(cover_file, 'avatars')
    
    music = UserMusic(
        user_id=current_user.id,
        title=title,
        artist=artist,
        file_url=filepath,
        cover_url=cover_url
    )
    db.session.add(music)
    db.session.commit()
    
    return jsonify({'success': True, 'id': music.id})


@api_bp.route('/music/<int:music_id>/delete', methods=['POST'])
@login_required
def delete_music(music_id):
    """Delete music from library"""
    music = UserMusic.query.get_or_404(music_id)
    
    if music.user_id != current_user.id:
        return jsonify({'error': 'Нет доступа'}), 403
    
    db.session.delete(music)
    db.session.commit()
    
    return jsonify({'success': True})


# --- MESSAGE ACTIONS ---

@api_bp.route('/message/<int:message_id>/delete', methods=['POST'])
@login_required
def delete_message(message_id):
    """Delete message"""
    message = Message.query.get_or_404(message_id)
    channel = Channel.query.get(message.channel_id)
    room = Room.query.get(channel.room_id) if channel else None
    
    if not room:
        return jsonify({'error': 'Комната не найдена'}), 404
    
    role = get_role(current_user.id, room.id)
    try:
        is_owner_message = int(message.user_id) == int(current_user.id)
    except Exception:
        is_owner_message = (message.user_id == current_user.id)
    can_delete = is_owner_message or (role in ['owner', 'admin'])
    
    if not can_delete:
        return jsonify({'error': 'Нет доступа'}), 403
    
    channel_id = message.channel_id
    db.session.delete(message)
    db.session.commit()
    
    socketio.emit('message_deleted', {
        'message_id': message_id,
        'channel_id': channel_id
    }, room=str(channel_id))
    
    return jsonify({'success': True})


@api_bp.route('/message/<int:message_id>/edit', methods=['POST'])
@login_required
def edit_message(message_id):
    """Edit message"""
    message = Message.query.get_or_404(message_id)
    
    if message.user_id != current_user.id:
        return jsonify({'error': 'Нет доступа'}), 403
    
    new_content = request.json.get('content', '')
    if new_content:
        message.content = new_content
        message.edited_at = datetime.utcnow()
        db.session.commit()
    
    # Load reactions
    reactions_data = {}
    for reaction in message.reactions:
        if reaction.emoji not in reactions_data:
            reactions_data[reaction.emoji] = []
        reactions_data[reaction.emoji].append(reaction.user.username)
    
    payload = {
        'message_id': message_id,
        'content': new_content,
        'channel_id': message.channel_id,
        'edited_at_iso': message.edited_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'reactions': reactions_data
    }

    # Emit to channel room so all connected clients (except possibly the editor) receive update
    socketio.emit('message_edited', payload, room=str(message.channel_id))

    # Return the payload along with success so the editing client can update immediately
    response = {'success': True}
    response.update(payload)
    return jsonify(response)


@api_bp.route('/message/<int:message_id>/forward', methods=['POST'])
@login_required
def forward_message(message_id):
    """Forward message to another channel"""
    message = Message.query.get_or_404(message_id)
    target_channel_id = request.json.get('channel_id')
    
    if not target_channel_id:
        return jsonify({'error': 'Не указан канал'}), 400
    
    target_channel = Channel.query.get(target_channel_id)
    if not target_channel:
        return jsonify({'error': 'Канал не найден'}), 404
    
    role = get_role(current_user.id, target_channel.room_id)
    if not role or role == 'banned':
        return jsonify({'error': 'Нет доступа'}), 403
    
    # Create forwarded message
    forwarded_content = f"Переслано от {message.user.username}:\n{message.content}"
    new_msg = Message(
        content=forwarded_content,
        user_id=current_user.id,
        channel_id=target_channel_id,
        message_type=message.message_type,
        file_url=message.file_url,
        file_name=message.file_name,
        file_size=message.file_size
    )
    db.session.add(new_msg)
    db.session.commit()
    
    socketio.emit('receive_message', {
        'id': new_msg.id,
        'user_id': current_user.id,
        'username': current_user.username,
        'avatar': current_user.avatar_url,
        'msg': forwarded_content,
        'timestamp_iso': new_msg.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'message_type': new_msg.message_type,
        'file_url': new_msg.file_url,
        'file_name': new_msg.file_name,
        'file_size': new_msg.file_size
    }, room=str(target_channel_id))
    
    return jsonify({'success': True})


@api_bp.route('/message/<int:message_id>/reaction', methods=['POST'])
@login_required
def toggle_reaction(message_id):
    """Add or remove reaction to message"""
    message = Message.query.get_or_404(message_id)
    emoji = request.json.get('emoji')
    reaction_type = request.json.get('reaction_type', 'emoji')
    
    if not emoji:
        return jsonify({'error': 'Не указана реакция'}), 400
    
    # Check if reaction already exists
    existing = MessageReaction.query.filter_by(
        message_id=message_id,
        user_id=current_user.id,
        emoji=emoji
    ).first()
    
    if existing:
        db.session.delete(existing)
        action = 'removed'
    else:
        reaction = MessageReaction(
            message_id=message_id,
            user_id=current_user.id,
            emoji=emoji,
            reaction_type=reaction_type
        )
        db.session.add(reaction)
        action = 'added'
    
    db.session.commit()
    
    # Get updated reactions
    reactions = MessageReaction.query.filter_by(message_id=message_id).all()
    reaction_data = {}
    for r in reactions:
        if r.emoji not in reaction_data:
            reaction_data[r.emoji] = []
        reaction_data[r.emoji].append(r.user.username)
    
    socketio.emit('reactions_updated', {
        'message_id': message_id,
        'reactions': reaction_data,
        'action': action,
        'emoji': emoji,
        'user': current_user.username
    }, room=str(message.channel_id))
    
    return jsonify({'success': True, 'action': action, 'reactions': reaction_data})


# --- ROOM MANAGEMENT ---

@api_bp.route('/room/<int:room_id>/delete', methods=['POST'])
@login_required
def delete_room(room_id):
    """Delete room"""
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    if not member:
        return jsonify({'error': 'Вы не являетесь участником'}), 403
    
    if member.role not in ['owner', 'admin']:
        return jsonify({'error': 'Нет прав для удаления сервера'}), 403
    
    # Delete all members first
    Member.query.filter_by(room_id=room_id).delete()
    # Delete room (cascade will delete channels and messages)
    db.session.delete(room)
    db.session.commit()
    
    return jsonify({'success': True})


@api_bp.route('/room/<int:room_id>/leave', methods=['POST'])
@login_required
def leave_room(room_id):
    """Leave room"""
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    if not member:
        return jsonify({'error': 'Вы не являетесь участником'}), 403
    
    if member.role == 'owner':
        return jsonify({'error': 'Владелец не может покинуть сервер. Удалите сервер вместо этого.'}), 403
    
    db.session.delete(member)
    db.session.commit()
    
    return jsonify({'success': True})


@api_bp.route('/room/<int:room_id>/delete_dm', methods=['POST'])
@login_required
def delete_dm(room_id):
    """Delete DM"""
    room = Room.query.get_or_404(room_id)
    
    if room.type != 'dm':
        return jsonify({'error': 'Это не личное сообщение'}), 400
    
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if not member:
        return jsonify({'error': 'Вы не являетесь участником'}), 403
    
    db.session.delete(member)
    db.session.commit()
    
    return jsonify({'success': True})


@api_bp.route('/room/<int:room_id>/invite', methods=['POST'])
@login_required
def generate_invite(room_id):
    """Generate invite link"""
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    if not member or member.role not in ['owner', 'admin']:
        return jsonify({'error': 'Нет прав для создания приглашений'}), 403
    
    import secrets
    if not room.invite_token:
        room.invite_token = secrets.token_urlsafe(32)
        db.session.commit()
    
    from flask import request as flask_request
    invite_url = flask_request.url_root.rstrip('/') + url_for('main.join_room_by_invite', token=room.invite_token)
    
    return jsonify({'success': True, 'invite_url': invite_url})


@api_bp.route('/join/<token>')
@login_required
def join_room_by_invite(token):
    """Join room by invite token"""
    room = Room.query.filter_by(invite_token=token).first_or_404()
    
    existing_member = Member.query.filter_by(user_id=current_user.id, room_id=room.id).first()
    if existing_member:
        return redirect(url_for('main.view_room', room_id=room.id))
    
    new_member = Member(user_id=current_user.id, room_id=room.id, role='member')
    db.session.add(new_member)
    db.session.commit()
    
    flash(f'Вы присоединились к {room.name}')
    return redirect(url_for('main.view_room', room_id=room.id))


@api_bp.route('/channels/accessible')
@login_required
def get_accessible_channels():
    """Get list of accessible channels for forwarding"""
    rooms = db.session.query(Room).join(Member).filter(
        Member.user_id == current_user.id
    ).all()
    
    channels_list = []
    for room in rooms:
        for channel in room.channels:
            channels_list.append({
                'id': channel.id,
                'name': channel.name,
                'room_id': room.id,
                'room_name': room.name,
                'room_type': room.type
            })
    
    return jsonify({'channels': channels_list})


# --- DESKTOP CLIENT API ENDPOINTS ---

@api_bp.route('/api/v1/user/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current user info - for desktop clients"""
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'avatar_url': current_user.avatar_url or 'https://via.placeholder.com/50',
        'bio': current_user.bio or '',
        'presence_status': current_user.presence_status or 'offline',
        'hide_status': current_user.hide_status or False,
        'is_superuser': current_user.is_superuser or False
    })


@api_bp.route('/api/v1/rooms', methods=['GET'])
@login_required
def get_user_rooms():
    """Get all rooms the user is member of - for desktop clients"""
    rooms_data = []
    rooms = Room.query.join(Member).filter(Member.user_id == current_user.id).all()
    
    for room in rooms:
        room_dict = {
            'id': room.id,
            'name': room.name,
            'type': room.type,
            'description': room.description,
            'avatar_url': room.avatar_url,
            'member_count': len(room.members),
            'channels': []
        }
        
        for channel in room.channels:
            channel_dict = {
                'id': channel.id,
                'name': channel.name,
                'description': channel.description,
                'icon_emoji': channel.icon_emoji,
                'icon_image_url': channel.icon_image_url
            }
            room_dict['channels'].append(channel_dict)
        
        rooms_data.append(room_dict)
    
    return jsonify({'rooms': rooms_data})


@api_bp.route('/api/v1/channel/<int:channel_id>/messages', methods=['GET'])
@login_required
def get_channel_messages(channel_id):
    """Get messages from a channel - for desktop clients"""
    channel = Channel.query.get_or_404(channel_id)
    room = channel.room
    
    # Check access
    member = Member.query.filter_by(user_id=current_user.id, room_id=room.id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    messages = Message.query.filter_by(channel_id=channel_id).order_by(
        Message.timestamp.desc()
    ).limit(limit).offset(offset).all()
    
    messages_data = []
    for msg in reversed(messages):
        reactions = {}
        for reaction in msg.reactions:
            if reaction.emoji not in reactions:
                reactions[reaction.emoji] = []
            reactions[reaction.emoji].append(reaction.user.username)
        
        msg_dict = {
            'id': msg.id,
            'user_id': msg.user_id,
            'username': msg.user.username if msg.user else 'Unknown',
            'avatar_url': msg.user.avatar_url if msg.user else None,
            'content': msg.content,
            'message_type': msg.message_type,
            'timestamp': msg.timestamp.isoformat(),
            'edited_at': msg.edited_at.isoformat() if msg.edited_at else None,
            'file_url': msg.file_url,
            'file_name': msg.file_name,
            'file_size': msg.file_size,
            'reactions': reactions,
            'reply_to_id': msg.reply_to_id
        }
        messages_data.append(msg_dict)
    
    return jsonify({'messages': messages_data, 'count': len(messages_data)})


@api_bp.route('/api/v1/user/<int:user_id>/profile', methods=['GET'])
@login_required
def get_user_profile(user_id):
    """Get user profile - for desktop clients"""
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'avatar_url': user.avatar_url or 'https://via.placeholder.com/50',
        'bio': user.bio or '',
        'presence_status': user.presence_status or 'offline' if not user.hide_status else 'hidden',
        'last_seen': user.last_seen.isoformat() if user.last_seen else None
    })


@api_bp.route('/api/v1/search/users', methods=['GET'])
@login_required
def search_users():
    """Search users by username - for desktop clients"""
    query = request.args.get('q', '', type=str).strip()
    if len(query) < 2:
        return jsonify({'error': 'Query too short', 'users': []}), 400
    
    users = User.query.filter(
        User.username.ilike(f'%{query}%'),
        User.privacy_searchable == True
    ).limit(20).all()
    
    users_data = [{
        'id': u.id,
        'username': u.username,
        'avatar_url': u.avatar_url or 'https://via.placeholder.com/50',
        'bio': u.bio or ''
    } for u in users]
    
    return jsonify({'users': users_data})


@api_bp.route('/api/v1/search/servers', methods=['GET'])
@login_required
def search_servers():
    """Search public servers - for desktop clients"""
    query = request.args.get('q', '', type=str).strip()
    if len(query) < 2:
        return jsonify({'error': 'Query too short', 'servers': []}), 400
    
    rooms = Room.query.filter(
        Room.name.ilike(f'%{query}%'),
        Room.type != 'dm'
    ).limit(20).all()
    
    rooms_data = [{
        'id': r.id,
        'name': r.name,
        'description': r.description or '',
        'type': r.type,
        'avatar_url': r.avatar_url or 'https://via.placeholder.com/100',
        'member_count': len(r.members)
    } for r in rooms]
    
    return jsonify({'servers': rooms_data})


@api_bp.route('/api/v1/dm/<int:user_id>/create', methods=['POST'])
@login_required
def create_dm(user_id):
    """Create or get DM with user - for desktop clients"""
    user = User.query.get_or_404(user_id)
    
    # Check if DM already exists
    existing_dm = Room.query.filter(
        Room.type == 'dm',
        Room.members.any(Member.user_id == current_user.id),
        Room.members.any(Member.user_id == user_id)
    ).first()
    
    if existing_dm:
        return jsonify({'success': True, 'room_id': existing_dm.id})
    
    # Create new DM
    dm = Room(name=f"DM: {current_user.username} - {user.username}", type='dm')
    db.session.add(dm)
    db.session.flush()
    
    # Add both users
    for uid in [current_user.id, user_id]:
        member = Member(user_id=uid, room_id=dm.id, role='owner')
        db.session.add(member)
    
    # Create default channel for DM
    channel = Channel(room_id=dm.id, name='general', emoji='💬')
    db.session.add(channel)
    db.session.commit()
    
    return jsonify({'success': True, 'room_id': dm.id})


@api_bp.route('/api/v1/room/<int:room_id>/join', methods=['POST'])
@login_required
def join_room_api(room_id):
    """Join a room - for desktop clients"""
    room = Room.query.get_or_404(room_id)
    
    # Check if already member
    existing = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if existing:
        return jsonify({'success': True, 'message': 'Already a member'})
    
    member = Member(user_id=current_user.id, room_id=room_id, role='member')
    db.session.add(member)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Joined room'})


@api_bp.route('/api/v1/statistics', methods=['GET'])
@login_required
def get_statistics():
    """Get user statistics - for desktop clients"""
    msg_count = Message.query.filter_by(user_id=current_user.id).count()
    room_count = Member.query.filter_by(user_id=current_user.id).count()
    
    return jsonify({
        'total_messages': msg_count,
        'total_rooms': room_count,
        'user_id': current_user.id
    })

