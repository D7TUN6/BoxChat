# API routes (uploads, settings, channel management, message actions)

import os
import re
import inspect
import json
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, send_from_directory, current_app
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func
from app.extensions import db, socketio
from app.models import (
    User, Room, Channel, Member, Message, UserMusic,
    MessageReaction, ReadMessage, RoomBan, Role, MemberRole, RoleMentionPermission
)
from app.functions import (
    save_uploaded_file, resize_image, is_image_file, is_music_file, is_video_file,
    normalize_role_tag, ensure_default_roles, ensure_user_default_roles, can_user_mention_role,
    ROLE_PERMISSION_KEYS, parse_role_permissions, get_user_permissions, user_has_room_permission
)
from app.routes.spa import send_spa_index
from app.routes.api_friends import register_friends_routes
from app.routes.api_search import register_search_routes

api_bp = Blueprint('api', __name__)

register_friends_routes(api_bp)
register_search_routes(api_bp)


def _get_giphy_key():
    try:
        from config import GIPHY_API_KEY
    except Exception:
        GIPHY_API_KEY = ''
    return os.environ.get('GIPHY_API_KEY') or (GIPHY_API_KEY or '')


def _serialize_giphy_item(g):
    try:
        gid = str(getattr(g, 'id', '') or '')
        title = str(getattr(g, 'title', '') or '')
        images = getattr(g, 'images', None)
        original = getattr(images, 'original', None) if images else None
        fixed = getattr(images, 'fixed_width_small', None) if images else None
        preview = getattr(images, 'preview_gif', None) if images else None
        url = getattr(original, 'url', None) if original else None
        prev = (
            (getattr(fixed, 'url', None) if fixed else None)
            or (getattr(preview, 'url', None) if preview else None)
            or url
        )
        if not url or not prev:
            return None
        return {
            'id': gid,
            'url': str(url),
            'preview': str(prev),
            'title': title,
        }
    except Exception:
        return None


def _giphy_call_with_optional_offset(api_instance, method_name: str, api_key: str, *, limit: int, offset: int, rating: str, q: str | None = None):
    method = getattr(api_instance, method_name)
    try:
        sig = inspect.signature(method)
        params = sig.parameters
        kwargs = {'limit': limit, 'rating': rating}
        if 'offset' in params:
            kwargs['offset'] = offset
        if q is not None and 'q' in params:
            kwargs['q'] = q
        # Some generated clients include q as positional 2nd arg (search)
        if q is not None:
            try:
                return method(api_key, q, **kwargs)
            except TypeError:
                return method(api_key, **kwargs)
        return method(api_key, **kwargs)
    except TypeError:
        pass

    # Fallback for older giphy-client versions: call through SDK ApiClient
    path = '/gifs/trending' if method_name == 'gifs_trending_get' else '/gifs/search'
    query_params = [('api_key', api_key), ('limit', int(limit)), ('rating', rating), ('offset', int(offset))]
    if q is not None:
        query_params.append(('q', q))

    # response_type varies between versions; try common ones.
    for response_type in ('InlineResponse200', 'object', None):
        try:
            return api_instance.api_client.call_api(
                path,
                'GET',
                query_params=query_params,
                response_type=response_type,
                auth_settings=[],
                _return_http_data_only=True,
            )
        except Exception:
            continue

    raise RuntimeError('Giphy SDK call failed')

# Helper functions
def get_role(user_id, room_id):
    # Get user role in room
    member = Member.query.filter_by(user_id=user_id, room_id=room_id).first()
    return member.role if member else None


def has_room_admin_access(user_id, room):
    if not room:
        return False
    member = Member.query.filter_by(user_id=user_id, room_id=room.id).first()
    return bool(member and member.role in ['owner', 'admin'])


def has_room_permission(user_id, room, permission_key: str):
    if not room:
        return False
    return bool(user_has_room_permission(int(user_id), int(room.id), permission_key))


def parse_duration_minutes(raw):
    token = str(raw or '').strip().lower()
    if not token:
        return None
    m = re.match(r'^(\d+)([mhd]?)$', token)
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


def get_active_room_ban(user_id: int, room_id: int):
    room_ban = RoomBan.query.filter_by(user_id=user_id, room_id=room_id).first()
    if not room_ban:
        return None
    if getattr(room_ban, 'banned_until', None) and room_ban.banned_until <= datetime.utcnow():
        try:
            db.session.delete(room_ban)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return None
    return room_ban


def save_file(file, subfolder='files'):
    # Wrapper for save_uploaded_file that uses current_app's upload folder
    return save_uploaded_file(file, subfolder, current_app.config['UPLOAD_FOLDER'])


def get_upload_folder():
    # Get upload folder from current app config
    return current_app.config.get('UPLOAD_FOLDER', 'uploads')


def _wants_json():
    if request.is_json:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept


def _emit_presence_update_for_user(user):
    memberships = Member.query.filter_by(user_id=user.id).all()
    for m in memberships:
        for ch in m.room.channels:
            socketio.emit('presence_updated', {
                'user_id': user.id,
                'username': user.username,
                'status': user.presence_status
            }, room=str(ch.id), skip_sid=None)

# --- CHANNEL MANAGEMENT ---

@api_bp.route('/room/<int:room_id>/add_channel', methods=['POST'])
@login_required
def add_channel(room_id):
    # Add channel to room
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_channels'):
        return jsonify({'error': 'Нет доступа'}), 403
    
    name = request.form.get('name')
    c = Channel(name=name, room_id=room_id)
    db.session.add(c)
    db.session.commit()
    
    return redirect(url_for('main.view_room', room_id=room_id))

@api_bp.route('/room/<int:room_id>/channel/<int:channel_id>/edit', methods=['POST'])
@login_required
def edit_channel(room_id, channel_id):
    # Edit channel
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_channels'):
        return jsonify({'error': 'Нет доступа'}), 403
    
    channel = Channel.query.get_or_404(channel_id)
    if channel.room_id != room_id:
        return jsonify({'error': 'Неверный канал'}), 400
    
    channel.name = request.form.get('name', channel.name)
    channel.description = request.form.get('description', channel.description)
    channel.icon_emoji = request.form.get('icon_emoji', channel.icon_emoji)
    writer_role_ids = request.form.get('writer_role_ids')
    if writer_role_ids is not None:
        try:
            parsed = json.loads(writer_role_ids)
            if isinstance(parsed, list):
                valid_roles = Role.query.filter(Role.room_id == room_id, Role.id.in_(parsed)).all()
                channel.writer_role_ids_json = json.dumps([int(r.id) for r in valid_roles])
        except Exception:
            pass
    
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
    # Delete channel
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_channels'):
        return jsonify({'error': 'Нет доступа'}), 403
    
    channel = Channel.query.get_or_404(channel_id)
    if channel.room_id != room_id:
        return jsonify({'error': 'Неверный канал'}), 400
    
    db.session.delete(channel)
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/api/v1/room/<int:room_id>/channel/<int:channel_id>/permissions', methods=['PATCH'])
@login_required
def update_channel_permissions(room_id, channel_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_channels'):
        return jsonify({'error': 'Access denied'}), 403
    channel = Channel.query.get_or_404(channel_id)
    if channel.room_id != room_id:
        return jsonify({'error': 'wrong channel'}), 400
    data = request.get_json(silent=True) or {}
    writer_role_ids = data.get('writer_role_ids', [])
    if not isinstance(writer_role_ids, list):
        return jsonify({'error': 'writer_role_ids must be list'}), 400
    valid_roles = Role.query.filter(Role.room_id == room_id, Role.id.in_(writer_role_ids)).all()
    channel.writer_role_ids_json = json.dumps([int(r.id) for r in valid_roles])
    db.session.commit()
    try:
        for m in Member.query.filter_by(room_id=room_id).all():
            socketio.emit('room_state_refresh', {'room_id': room_id}, room=f"user_{m.user_id}")
    except Exception:
        pass
    return jsonify({'success': True, 'writer_role_ids': json.loads(channel.writer_role_ids_json or '[]')})

# --- USER SETTINGS ---

@api_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Keep legacy path, but serve SPA on GET
    if request.method == 'GET':
        return send_spa_index()

    current_user.bio = request.form.get('bio', current_user.bio)
    current_user.privacy_searchable = 'privacy_searchable' in request.form
    current_user.privacy_listable = 'privacy_listable' in request.form

    if 'hide_status' in request.form:
        current_user.hide_status = True
        current_user.presence_status = 'hidden'
    else:
        current_user.hide_status = False
        if current_user.presence_status != 'away':
            current_user.presence_status = 'online'

    if 'avatar_file' in request.files:
        file = request.files['avatar_file']
        if file and file.filename:
            filepath = save_file(file, 'avatars')
            if filepath:
                current_user.avatar_url = filepath

    db.session.commit()
    _emit_presence_update_for_user(current_user)

    if _wants_json():
        return jsonify({'success': True})

    flash('Settings updated')
    return redirect(url_for('api.settings'))


@api_bp.route('/api/v1/user/settings', methods=['GET', 'PATCH'])
@login_required
def user_settings_api():
    if request.method == 'GET':
        return jsonify({
            'id': current_user.id,
            'username': current_user.username,
            'avatar_url': current_user.avatar_url or 'https://placehold.co/50x50',
            'bio': current_user.bio or '',
            'privacy_searchable': bool(current_user.privacy_searchable),
            'privacy_listable': bool(current_user.privacy_listable),
            'hide_status': bool(current_user.hide_status),
            'presence_status': current_user.presence_status or 'offline',
        })

    data = request.get_json(silent=True) or {}
    if 'bio' in data:
        current_user.bio = str(data.get('bio') or '')[:300]
    if 'username' in data:
        next_username = str(data.get('username') or '').strip()
        if len(next_username) < 3 or len(next_username) > 30:
            return jsonify({'error': 'username should be 3..30 characters long'}), 400
        if not re.match(r'^[a-zA-Z0-9_-]+$', next_username):
            return jsonify({'error': 'username can only contain letters, numbers, hyphens, and underscores'}), 400
        exists = User.query.filter(
            func.lower(User.username) == next_username.lower(),
            User.id != current_user.id
        ).first()
        if exists:
            return jsonify({'error': 'username already taken'}), 409
        current_user.username = next_username
    if 'privacy_searchable' in data:
        current_user.privacy_searchable = bool(data.get('privacy_searchable'))
    if 'privacy_listable' in data:
        current_user.privacy_listable = bool(data.get('privacy_listable'))
    if 'hide_status' in data:
        current_user.hide_status = bool(data.get('hide_status'))
        if current_user.hide_status:
            current_user.presence_status = 'hidden'
        elif current_user.presence_status != 'away':
            current_user.presence_status = 'online'

    db.session.commit()
    _emit_presence_update_for_user(current_user)

    return jsonify({'success': True})


@api_bp.route('/api/v1/user/avatar', methods=['POST'])
@login_required
def upload_user_avatar_api():
    if 'avatar' not in request.files:
        return jsonify({'error': 'avatar file is required'}), 400

    file = request.files['avatar']
    if not file or not file.filename:
        return jsonify({'error': 'avatar file is required'}), 400

    filepath = save_file(file, 'avatars')
    if not filepath:
        return jsonify({'error': 'failed to save avatar'}), 500

    current_user.avatar_url = filepath
    db.session.commit()
    return jsonify({'success': True, 'avatar_url': current_user.avatar_url})

@api_bp.route('/user/avatar/delete', methods=['POST'])
@login_required
def delete_user_avatar():
    # Delete user avatar
    if current_user.avatar_url and current_user.avatar_url != "https://placehold.co/50x50":
        if current_user.avatar_url.startswith('/uploads/'):
            try:
                filename = current_user.avatar_url.lstrip('/uploads/').lstrip('/')
                abs_path = os.path.join(get_upload_folder(), filename)
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except:
                pass
        
        current_user.avatar_url = "https://placehold.co/50x50"
        db.session.commit()
    
    return jsonify({'success': True})


@api_bp.route('/user/delete', methods=['POST'])
@login_required
def delete_user_account():
    # Delete user account and all associated data
    data = request.json
    password = data.get('password')
    
    if not password:
        return jsonify({'error': 'no password specified'}), 400
    
    if not check_password_hash(current_user.password, password):
        return jsonify({'error': 'wrond password'}), 403
    
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
        return jsonify({'error': f'error while deleting account {str(e)}'}), 500

# --- ROOM SETTINGS ---

@api_bp.route('/room/<int:room_id>/settings', methods=['GET', 'POST'])
@login_required
def room_settings(room_id):
    # Room settings page
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
    
    # Get banned users from RoomBan table
    room_bans = RoomBan.query.filter_by(room_id=room_id).all()
    
    return render_template('room_settings.html', room=room, room_bans=room_bans)


@api_bp.route('/channel/<int:channel_id>/mark_read', methods=['POST'])
@login_required
def mark_channel_read(channel_id):
    # Mark channel as read for current user (set last_read to last message)
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
    # Delete room avatar
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_server'):
        return jsonify({'error': 'no rights'}), 403
    
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
    # Upload file (image, music, or document
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'error': 'file not selected'}), 400
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
        return jsonify({'error': 'error saving file'}), 500

    # Ensure filename is returned (basename of saved path)
    try:
        filename = os.path.basename(filepath)
    except Exception:
        filename = file.filename

    return jsonify({'success': True, 'url': filepath, 'type': filetype, 'filename': filename})

@api_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Serve uploaded file
    return send_from_directory(get_upload_folder(), filename)

@api_bp.route('/music/add', methods=['POST'])
@login_required
def add_music():
    # Add music to user library
    if 'music_file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    
    file = request.files['music_file']
    if not file or not file.filename or not is_music_file(file.filename):
        return jsonify({'error': 'wrong music format'}), 400
    
    filepath = save_file(file, 'music')
    if not filepath:
        return jsonify({'error': 'upload error'}), 500
    
    title = request.form.get('title', 'Unknown')
    artist = request.form.get('artist', 'Unknown artist')
    
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
    # Delete music from library
    music = UserMusic.query.get_or_404(music_id)
    
    if music.user_id != current_user.id:
        return jsonify({'error': 'no access'}), 403
    
    db.session.delete(music)
    db.session.commit()
    
    return jsonify({'success': True})

# --- MESSAGE ACTIONS ---

@api_bp.route('/api/v1/reactions', methods=['GET'])
@login_required
def list_reactions():
    return jsonify({
        'reactions': [
            '👍', '❤️', '😂', '😈', '😢', '🔥', '🎉', '🥲', '✅', '❌'
        ]
    })


@api_bp.route('/api/v1/gifs/trending', methods=['GET'])
@login_required
def gifs_trending():
    api_key = _get_giphy_key()
    if not api_key:
        return jsonify({'error': 'GIPHY_API_KEY is not configured'}), 500

    limit = request.args.get('limit', 24, type=int)
    offset = request.args.get('offset', 0, type=int)
    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50
    if offset < 0:
        offset = 0

    try:
        import giphy_client
        from giphy_client.rest import ApiException

        api_instance = giphy_client.DefaultApi()
        res = _giphy_call_with_optional_offset(api_instance, 'gifs_trending_get', api_key, limit=limit, offset=offset, rating='pg-13')
        items = []
        for g in (getattr(res, 'data', None) or []):
            mapped = _serialize_giphy_item(g)
            if mapped:
                items.append(mapped)
        pagination = getattr(res, 'pagination', None)
        total = getattr(pagination, 'total_count', None) if pagination else None
        count = getattr(pagination, 'count', None) if pagination else None
        next_offset = offset + (int(count) if isinstance(count, int) else len(items))
        return jsonify({'gifs': items, 'pagination': {'offset': offset, 'limit': limit, 'total': total, 'next_offset': next_offset}})
    except Exception as e:
        return jsonify({'error': f'Failed to load trending gifs: {str(e)}'}), 500


@api_bp.route('/api/v1/gifs/search', methods=['GET'])
@login_required
def gifs_search():
    api_key = _get_giphy_key()
    if not api_key:
        return jsonify({'error': 'GIPHY_API_KEY is not configured'}), 500

    q = request.args.get('q', '', type=str).strip()
    if not q:
        return jsonify({'gifs': [], 'pagination': {'offset': 0, 'limit': 0, 'total': 0, 'next_offset': 0}})

    limit = request.args.get('limit', 24, type=int)
    offset = request.args.get('offset', 0, type=int)
    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50
    if offset < 0:
        offset = 0

    try:
        import giphy_client
        from giphy_client.rest import ApiException

        api_instance = giphy_client.DefaultApi()
        res = _giphy_call_with_optional_offset(api_instance, 'gifs_search_get', api_key, limit=limit, offset=offset, rating='pg-13', q=q)
        items = []
        for g in (getattr(res, 'data', None) or []):
            mapped = _serialize_giphy_item(g)
            if mapped:
                items.append(mapped)
        pagination = getattr(res, 'pagination', None)
        total = getattr(pagination, 'total_count', None) if pagination else None
        count = getattr(pagination, 'count', None) if pagination else None
        next_offset = offset + (int(count) if isinstance(count, int) else len(items))
        return jsonify({'gifs': items, 'pagination': {'offset': offset, 'limit': limit, 'total': total, 'next_offset': next_offset}})
    except Exception as e:
        return jsonify({'error': f'Failed to search gifs: {str(e)}'}), 500

@api_bp.route('/message/<int:message_id>/delete', methods=['POST'])
@login_required
def delete_message(message_id):
    # Delete message
    message = Message.query.get_or_404(message_id)
    channel = Channel.query.get(message.channel_id)
    room = Room.query.get(channel.room_id) if channel else None
    
    if not room:
        return jsonify({'error': 'room not found'}), 404
    
    try:
        is_owner_message = int(message.user_id) == int(current_user.id)
    except Exception:
        is_owner_message = (message.user_id == current_user.id)
    can_delete = is_owner_message or has_room_permission(current_user.id, room, 'delete_messages')
    
    if not can_delete:
        return jsonify({'error': 'no access'}), 403
    
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
    # Edit message
    message = Message.query.get_or_404(message_id)
    
    if message.user_id != current_user.id:
        return jsonify({'error': 'no access'}), 403
    
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
    # Forward message
    message = Message.query.get_or_404(message_id)
    target_channel_id = request.json.get('channel_id')
    
    if not target_channel_id:
        return jsonify({'error': 'channel not specified'}), 400
    
    target_channel = Channel.query.get(target_channel_id)
    if not target_channel:
        return jsonify({'error': 'channel not found'}), 404
    
    role = get_role(current_user.id, target_channel.room_id)
    if not role or role == 'banned':
        return jsonify({'error': 'no access'}), 403
    
    # Create forwarded message
    forwarded_content = f"Forwarded from {message.user.username}:\n{message.content}"
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
    # Add or remove reaction to message
    message = Message.query.get_or_404(message_id)
    emoji = request.json.get('emoji')
    reaction_type = request.json.get('reaction_type', 'emoji')
    
    if not emoji:
        return jsonify({'error': 'reaction not specified'}), 400
    
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
    # Delete room
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if not member:
        return jsonify({'error': 'you are not a member'}), 403
    if not has_room_permission(current_user.id, room, 'delete_server'):
        return jsonify({'error': 'no rights to delete the server'}), 403
    
    # Delete all members first
    Member.query.filter_by(room_id=room_id).delete()
    # Delete room (cascade will delete channels and messages)
    db.session.delete(room)
    db.session.commit()
    
    return jsonify({'success': True})

@api_bp.route('/room/<int:room_id>/leave', methods=['POST'])
@login_required
def leave_room(room_id):
    # Leave room
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    if not member:
        return jsonify({'error': 'you are not a member'}), 403
    
    if member.role == 'owner':
        return jsonify({'error': 'owner cannot leave his server, delete server for this'}), 403
    
    # Prevent banned users from leaving (to preserve their ban record)
    # Check if user is banned from this room
    room_ban = get_active_room_ban(current_user.id, room_id)
    if room_ban:
        print(f"[LEAVE ROOM] User {current_user.id} attempted to leave while banned from room {room_id}")
        return jsonify({'error': 'you are banned from this server'}), 403
    
    print(f"[LEAVE ROOM] User {current_user.id} left room {room_id}")
    db.session.delete(member)
    db.session.commit()
    
    return jsonify({'success': True})

@api_bp.route('/room/<int:room_id>/delete_dm', methods=['POST'])
@login_required
def delete_dm(room_id):
    # Delete DM
    room = Room.query.get_or_404(room_id)
    
    if room.type != 'dm':
        return jsonify({'error': 'this is not a dm'}), 400
    
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if not member:
        return jsonify({'error': 'you are not a member'}), 403
    
    db.session.delete(member)
    db.session.commit()
    
    return jsonify({'success': True})

@api_bp.route('/room/<int:room_id>/invite', methods=['POST'])
@login_required
def generate_invite(room_id):
    # Generate invite link
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if not member:
        return jsonify({'error': 'no membership'}), 403
    if not has_room_permission(current_user.id, room, 'invite_members'):
        return jsonify({'error': 'no rights to create a invite'}), 403
    
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
    # Join room by invite token
    room = Room.query.filter_by(invite_token=token).first_or_404()
    
    room_ban = get_active_room_ban(current_user.id, room.id)
    if room_ban:
        return jsonify({'error': 'you are banned in this room'}), 403

    existing_member = Member.query.filter_by(user_id=current_user.id, room_id=room.id).first()
    if existing_member:
        return redirect(url_for('main.view_room', room_id=room.id))
    
    new_member = Member(user_id=current_user.id, room_id=room.id, role='member')
    db.session.add(new_member)
    db.session.commit()

    ensure_default_roles(room.id)
    ensure_user_default_roles(current_user.id, room.id)
    db.session.commit()
    
    flash(f'you have joined {room.name}')
    return redirect(url_for('main.view_room', room_id=room.id))

@api_bp.route('/channels/accessible')
@login_required
def get_accessible_channels():
    # Get list of accessible channels for forwarding
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

# --- (future) DESKTOP CLIENT API ENDPOINTS ---

@api_bp.route('/api/v1/user/me', methods=['GET'])
@login_required
def get_current_user():
    # Get current user info - for desktop clients
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'avatar_url': current_user.avatar_url or 'https://placehold.co/50x50',
        'bio': current_user.bio or '',
        'presence_status': current_user.presence_status or 'offline',
        'hide_status': current_user.hide_status or False,
        'is_superuser': current_user.is_superuser or False
    })

@api_bp.route('/api/v1/rooms', methods=['GET'])
@login_required
def get_user_rooms():
    # Get all rooms the user is member of - for desktop clients
    rooms_data = []
    rooms = Room.query.join(Member).filter(Member.user_id == current_user.id).all()
    
    for room in rooms:
        my_member = Member.query.filter_by(user_id=current_user.id, room_id=room.id).first()
        perms = get_user_permissions(current_user.id, room.id)
        room_name = room.name
        if room.type == 'dm':
            try:
                other_member = next((m for m in room.members if int(m.user_id) != int(current_user.id)), None)
                if other_member and other_member.user and other_member.user.username:
                    room_name = other_member.user.username
            except Exception:
                room_name = room.name

        room_dict = {
            'id': room.id,
            'name': room_name,
            'type': room.type,
            'my_role': my_member.role if my_member else 'member',
            'my_permissions': sorted(list(perms)),
            'is_public': bool(room.is_public),
            'description': getattr(room, 'description', None) or '',
            'avatar_url': room.avatar_url,
            'banner_url': getattr(room, 'banner_url', None),
            'member_count': len(room.members),
            'channels': []
        }
        
        for channel in room.channels:
            channel_dict = {
                'id': channel.id,
                'name': channel.name,
                'description': channel.description,
                'icon_emoji': channel.icon_emoji,
                'icon_image_url': channel.icon_image_url,
                'writer_role_ids': json.loads(channel.writer_role_ids_json or '[]') if getattr(channel, 'writer_role_ids_json', None) else [],
            }
            room_dict['channels'].append(channel_dict)
        
        rooms_data.append(room_dict)
    
    return jsonify({'rooms': rooms_data})


@api_bp.route('/api/v1/room/<int:room_id>/members', methods=['GET'])
@login_required
def get_room_members(room_id):
    # Members list for mentions/autocomplete in SPA
    room = Room.query.get_or_404(room_id)
    membership = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if not membership:
        return jsonify({'error': 'Access denied'}), 403

    members = Member.query.filter_by(room_id=room_id).all()
    role_links = MemberRole.query.filter_by(room_id=room_id).all()
    role_map = {}
    for link in role_links:
        role_map.setdefault(link.user_id, []).append(link.role_id)
    payload = []
    for m in members:
        if not m.user:
            continue
        payload.append({
            'id': m.user.id,
            'username': m.user.username,
            'avatar_url': m.user.avatar_url or 'https://placehold.co/50x50',
            'role': m.role,
            'role_ids': sorted(role_map.get(m.user.id, [])),
            'presence_status': 'hidden' if getattr(m.user, 'hide_status', False) else (m.user.presence_status or 'offline'),
            'muted_until': m.muted_until.isoformat() if getattr(m, 'muted_until', None) else None,
        })

    payload.sort(key=lambda u: u['username'].lower())
    return jsonify({'room_id': room_id, 'members': payload})


@api_bp.route('/api/v1/room/<int:room_id>/settings', methods=['GET', 'PATCH'])
@login_required
def room_settings_api(room_id):
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403

    if request.method == 'GET':
        perms = get_user_permissions(current_user.id, room_id)
        return jsonify({
            'id': room.id,
            'name': room.name,
            'description': (room.description or ''),
            'type': room.type,
            'is_public': bool(room.is_public),
            'owner_id': room.owner_id,
            'avatar_url': room.avatar_url,
            'banner_url': room.banner_url,
            'permissions': {
                'can_manage_server': has_room_permission(current_user.id, room, 'manage_server'),
                'can_manage_roles': has_room_permission(current_user.id, room, 'manage_roles'),
                'can_manage_channels': has_room_permission(current_user.id, room, 'manage_channels'),
                'can_invite_members': has_room_permission(current_user.id, room, 'invite_members'),
                'can_delete_server': has_room_permission(current_user.id, room, 'delete_server'),
                'can_delete_messages': has_room_permission(current_user.id, room, 'delete_messages'),
                'can_kick_members': has_room_permission(current_user.id, room, 'kick_members'),
                'can_ban_members': has_room_permission(current_user.id, room, 'ban_members'),
                'can_mute_members': has_room_permission(current_user.id, room, 'mute_members'),
                'granted_permissions': sorted(list(perms)),
            }
        })

    if not has_room_permission(current_user.id, room, 'manage_server'):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        next_name = str(data.get('name') or '').strip()
        if len(next_name) < 2 or len(next_name) > 150:
            return jsonify({'error': 'room name must be 2..150 chars'}), 400
        room.name = next_name
    if 'description' in data:
        room.description = str(data.get('description') or '').strip()[:500]
    if 'is_public' in data:
        room.is_public = bool(data.get('is_public'))

    db.session.commit()
    return jsonify({
        'success': True,
        'room': {
            'id': room.id,
            'name': room.name,
            'description': room.description or '',
            'is_public': bool(room.is_public),
            'avatar_url': room.avatar_url,
            'banner_url': room.banner_url,
        }
    })


@api_bp.route('/api/v1/room/<int:room_id>/avatar', methods=['POST'])
@login_required
def upload_room_avatar_api(room_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_server'):
        return jsonify({'error': 'Access denied'}), 403
    if 'avatar' not in request.files:
        return jsonify({'error': 'avatar file is required'}), 400
    file = request.files['avatar']
    if not file or not file.filename:
        return jsonify({'error': 'avatar file is required'}), 400
    filepath = save_file(file, 'room_avatars')
    if not filepath:
        return jsonify({'error': 'failed to save avatar'}), 500
    room.avatar_url = filepath
    db.session.commit()
    return jsonify({'success': True, 'avatar_url': room.avatar_url})


@api_bp.route('/api/v1/room/<int:room_id>/banner', methods=['POST'])
@login_required
def upload_room_banner_api(room_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_server'):
        return jsonify({'error': 'Access denied'}), 403
    if 'banner' not in request.files:
        return jsonify({'error': 'banner file is required'}), 400
    file = request.files['banner']
    if not file or not file.filename:
        return jsonify({'error': 'banner file is required'}), 400
    filepath = save_file(file, 'room_avatars')
    if not filepath:
        return jsonify({'error': 'failed to save banner'}), 500
    room.banner_url = filepath
    db.session.commit()
    return jsonify({'success': True, 'banner_url': room.banner_url})


@api_bp.route('/api/v1/room/<int:room_id>/banner/delete', methods=['POST'])
@login_required
def delete_room_banner_api(room_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_server'):
        return jsonify({'error': 'Access denied'}), 403
    room.banner_url = None
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/api/v1/room/<int:room_id>/roles', methods=['GET'])
@login_required
def get_room_roles(room_id):
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403

    ensure_default_roles(room_id)
    db.session.commit()

    roles = Role.query.filter_by(room_id=room_id).all()
    data = []
    for role in roles:
        allowed_source_roles = [
            p.source_role_id
            for p in RoleMentionPermission.query.filter_by(room_id=room_id, target_role_id=role.id).all()
        ]
        data.append({
            'id': role.id,
            'name': role.name,
            'mention_tag': role.mention_tag,
            'is_system': bool(role.is_system),
            'can_be_mentioned_by_everyone': bool(role.can_be_mentioned_by_everyone),
            'allowed_source_role_ids': allowed_source_roles,
            'permissions': sorted(list(parse_role_permissions(role))),
        })

    data.sort(key=lambda r: r['name'].lower())
    return jsonify({'room_id': room_id, 'roles': data})


@api_bp.route('/api/v1/room/<int:room_id>/roles', methods=['POST'])
@login_required
def create_room_role(room_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_roles'):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or '').strip()
    if len(name) < 2 or len(name) > 60:
        return jsonify({'error': 'role name must be 2..60 chars'}), 400

    mention_tag = normalize_role_tag(name)
    if len(mention_tag) < 2:
        return jsonify({'error': 'role name is invalid'}), 400

    exists = Role.query.filter_by(room_id=room_id, mention_tag=mention_tag).first()
    if exists:
        return jsonify({'error': 'role already exists'}), 409

    role = Role(
        room_id=room_id,
        name=name,
        mention_tag=mention_tag,
        is_system=False,
        can_be_mentioned_by_everyone=bool(data.get('can_be_mentioned_by_everyone', False)),
        permissions_json=json.dumps([p for p in data.get('permissions', []) if p in ROLE_PERMISSION_KEYS]),
    )
    db.session.add(role)
    db.session.commit()
    return jsonify({'success': True, 'role_id': role.id})


@api_bp.route('/api/v1/room/<int:room_id>/roles/<int:role_id>', methods=['PATCH'])
@login_required
def update_room_role(room_id, role_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_roles'):
        return jsonify({'error': 'Access denied'}), 403

    role = Role.query.filter_by(id=role_id, room_id=room_id).first_or_404()
    data = request.get_json(silent=True) or {}

    if 'can_be_mentioned_by_everyone' in data:
        role.can_be_mentioned_by_everyone = bool(data.get('can_be_mentioned_by_everyone'))

    if not role.is_system and 'name' in data:
        new_name = str(data.get('name') or '').strip()
        if len(new_name) < 2 or len(new_name) > 60:
            return jsonify({'error': 'role name must be 2..60 chars'}), 400
        new_tag = normalize_role_tag(new_name)
        exists = Role.query.filter(
            Role.room_id == room_id,
            Role.mention_tag == new_tag,
            Role.id != role.id
        ).first()
        if exists:
            return jsonify({'error': 'role name already exists'}), 409
        role.name = new_name
        role.mention_tag = new_tag

    if 'permissions' in data:
        perms = data.get('permissions', [])
        if not isinstance(perms, list):
            return jsonify({'error': 'permissions must be list'}), 400
        cleaned = [p for p in perms if p in ROLE_PERMISSION_KEYS]
        role.permissions_json = json.dumps(sorted(list(set(cleaned))))

    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/api/v1/room/<int:room_id>/roles/<int:role_id>', methods=['DELETE'])
@login_required
def delete_room_role(room_id, role_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_roles'):
        return jsonify({'error': 'Access denied'}), 403

    role = Role.query.filter_by(id=role_id, room_id=room_id).first_or_404()
    if role.is_system:
        return jsonify({'error': 'cannot delete system role'}), 400

    RoleMentionPermission.query.filter(
        RoleMentionPermission.room_id == room_id,
        or_(
            RoleMentionPermission.source_role_id == role.id,
            RoleMentionPermission.target_role_id == role.id,
        )
    ).delete(synchronize_session=False)
    MemberRole.query.filter_by(room_id=room_id, role_id=role.id).delete(synchronize_session=False)
    db.session.delete(role)
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/api/v1/room/<int:room_id>/roles/<int:target_role_id>/mentioners', methods=['PATCH'])
@login_required
def update_role_mention_permissions(room_id, target_role_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_roles'):
        return jsonify({'error': 'Access denied'}), 403

    target_role = Role.query.filter_by(id=target_role_id, room_id=room_id).first_or_404()
    data = request.get_json(silent=True) or {}
    source_role_ids = data.get('source_role_ids', [])
    if not isinstance(source_role_ids, list):
        return jsonify({'error': 'source_role_ids must be list'}), 400

    valid_roles = Role.query.filter(Role.room_id == room_id, Role.id.in_(source_role_ids)).all()
    valid_ids = {r.id for r in valid_roles}

    existing = RoleMentionPermission.query.filter_by(room_id=room_id, target_role_id=target_role.id).all()
    for perm in existing:
        if perm.source_role_id not in valid_ids:
            db.session.delete(perm)

    existing_ids = {perm.source_role_id for perm in existing}
    for rid in valid_ids:
        if rid not in existing_ids:
            db.session.add(RoleMentionPermission(
                room_id=room_id,
                source_role_id=rid,
                target_role_id=target_role.id
            ))

    db.session.commit()
    return jsonify({'success': True, 'target_role_id': target_role.id, 'source_role_ids': sorted(valid_ids)})


@api_bp.route('/api/v1/room/<int:room_id>/members/<int:user_id>/roles', methods=['PATCH'])
@login_required
def assign_member_roles(room_id, user_id):
    room = Room.query.get_or_404(room_id)
    if not has_room_permission(current_user.id, room, 'manage_roles'):
        return jsonify({'error': 'Access denied'}), 403

    member = Member.query.filter_by(room_id=room_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'member not found'}), 404

    data = request.get_json(silent=True) or {}
    role_ids = data.get('role_ids', [])
    if not isinstance(role_ids, list):
        return jsonify({'error': 'role_ids must be list'}), 400

    ensure_default_roles(room_id)
    db.session.flush()

    everyone = Role.query.filter_by(room_id=room_id, mention_tag='everyone').first()
    admin_role = Role.query.filter_by(room_id=room_id, mention_tag='admin').first()

    valid_roles = Role.query.filter(Role.room_id == room_id, Role.id.in_(role_ids)).all()
    valid_ids = {r.id for r in valid_roles}
    if everyone:
        valid_ids.add(everyone.id)  # everyone must always be present

    existing_links = MemberRole.query.filter_by(room_id=room_id, user_id=user_id).all()
    existing_ids = {l.role_id for l in existing_links}

    for link in existing_links:
        if link.role_id not in valid_ids:
            db.session.delete(link)
    for rid in valid_ids:
        if rid not in existing_ids:
            db.session.add(MemberRole(room_id=room_id, user_id=user_id, role_id=rid))

    # Keep legacy member.role in sync with admin role
    if admin_role and admin_role.id in valid_ids and member.role == 'member':
        member.role = 'admin'
    if admin_role and admin_role.id not in valid_ids and member.role == 'admin':
        member.role = 'member'

    db.session.commit()
    try:
        for m in Member.query.filter_by(room_id=room_id).all():
            socketio.emit('room_state_refresh', {'room_id': room_id}, room=f"user_{m.user_id}")
    except Exception:
        pass
    return jsonify({'success': True, 'user_id': user_id, 'role_ids': sorted(valid_ids)})

@api_bp.route('/api/v1/channel/<int:channel_id>/messages', methods=['GET'])
@login_required
def get_channel_messages(channel_id):
    # Get messages from a channel - for desktop clients
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
    # Get user profile - for desktop clients
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'avatar_url': user.avatar_url or 'https://placehold.co/50x50',
        'bio': user.bio or '',
        'presence_status': user.presence_status or 'offline' if not user.hide_status else 'hidden',
        'last_seen': user.last_seen.isoformat() if user.last_seen else None
    })

@api_bp.route('/api/v1/room/<int:room_id>/join', methods=['POST'])
@login_required
def join_room_api(room_id):
    # Join a room - for desktop clients
    room = Room.query.get_or_404(room_id)
    # Block globally banned users
    if getattr(current_user, 'is_banned', False):
        return jsonify({'error': 'your accound is blocked'}), 403

    room_ban = get_active_room_ban(current_user.id, room_id)
    if room_ban:
        return jsonify({'error': 'you are banned in this room'}), 403

    # Check if already member
    existing = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if existing:
        # If membership exists but is 'banned', prevent join
        if existing.role == 'banned':
            return jsonify({'error': 'you are banned in this room'}), 403
        return jsonify({'success': True, 'message': 'Already a member'})

    member = Member(user_id=current_user.id, room_id=room_id, role='member')
    db.session.add(member)
    db.session.commit()

    ensure_default_roles(room_id)
    ensure_user_default_roles(current_user.id, room_id)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Joined room'})

@api_bp.route('/api/v1/statistics', methods=['GET'])
@login_required
def get_statistics():
    # Get user statistics - for desktop clients
    msg_count = Message.query.filter_by(user_id=current_user.id).count()
    room_count = Member.query.filter_by(user_id=current_user.id).count()
    
    return jsonify({
        'total_messages': msg_count,
        'total_rooms': room_count,
        'user_id': current_user.id
    })

# --- ADMIN FUNCTIONS ---

def get_client_ip():
    # Safely get client IP address
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

@api_bp.route('/admin/user/<int:user_id>/ban', methods=['POST'])
@login_required
def ban_user(user_id):
    # Ban user by admin - blocks by IP and marks as banned
    user = User.query.get_or_404(user_id)
    
    if user.is_superuser:
        return jsonify({'error': 'its impossible to ban an admin'}), 403
    
    data = request.json or {}
    ban_reason = data.get('reason', 'tos violation')
    ban_ip = data.get('ban_ip', True)
    duration_raw = data.get('duration') or data.get('ban_duration') or data.get('ban_for')
    minutes_raw = data.get('ban_minutes')
    duration_minutes = None
    if minutes_raw is not None and str(minutes_raw).strip() != '':
        try:
            duration_minutes = max(1, int(minutes_raw))
        except Exception:
            duration_minutes = None
    if duration_minutes is None:
        duration_minutes = parse_duration_minutes(duration_raw)
    banned_until = datetime.utcnow() + timedelta(minutes=duration_minutes) if duration_minutes else None
    room_id = data.get('room_id')
    try:
        room_id = int(room_id) if room_id is not None and room_id != '' else None
    except Exception:
        room_id = None

    # If room_id provided, allow room owner/admins to ban within that room
    if room_id:
        admin_member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
        room = Room.query.get(room_id)
        # Allow if requester is room owner, room admin, or global superuser
        allowed = False
        if current_user.is_superuser:
            allowed = True
        if room and has_room_permission(current_user.id, room, 'ban_members'):
            allowed = True
        if not allowed:
            debug = {
                'current_user_id': current_user.id,
                'room_id': room_id,
                'room_owner_id': room.owner_id if room else None,
                'admin_member_role': admin_member.role if admin_member else None
            }
            return jsonify({'error': 'not enough rights to ban in this room', 'debug': debug}), 403

        # Mark target membership as 'banned' so it can be unbanned later
        target_membership = Member.query.filter_by(user_id=user_id, room_id=room_id).first()
        if target_membership:
            # Optional deletion of messages in room
            if data.get('delete_messages'):
                try:
                    channel_ids = [c.id for c in target_membership.room.channels]
                    if channel_ids:
                        deleted = Message.query.filter(Message.user_id == user_id, Message.channel_id.in_(channel_ids)).delete(synchronize_session=False)
                        db.session.commit()
                        try:
                            socketio.emit('bulk_messages_deleted', {'user_id': user_id, 'room_id': room_id, 'deleted': deleted}, room=str(room_id))
                        except Exception:
                            pass
                except Exception:
                    db.session.rollback()

            # Create RoomBan record
            existing_ban = RoomBan.query.filter_by(user_id=user_id, room_id=room_id).first()
            if not existing_ban:
                room_ban = RoomBan(
                    room_id=room_id,
                    user_id=user_id,
                    banned_by_id=current_user.id,
                    reason=ban_reason,
                    banned_until=banned_until,
                    messages_deleted=data.get('delete_messages', False)
                )
                db.session.add(room_ban)
            else:
                existing_ban.reason = ban_reason
                existing_ban.banned_by_id = current_user.id
                existing_ban.banned_until = banned_until
                existing_ban.messages_deleted = bool(data.get('delete_messages', False))
            
            # Delete the member record so server doesn't appear in dashboard
            db.session.delete(target_membership)
            db.session.commit()

            # Notify room members to remove this member from UI
            try:
                socketio.emit('member_removed', {'user_id': user_id, 'room_id': room_id}, room=str(room_id))
            except Exception:
                pass

            # Notify the banned user in real-time to redirect them
            try:
                socketio.emit('force_redirect', {
                    'location': '/',
                    'reason': f'You have been banned from {room.name if room else "this room"}. Reason: {ban_reason}'
                }, room=f"user_{user_id}")
            except Exception:
                pass

            return jsonify({
                'success': True,
                'message': f'user {user.username} banned in room',
                'room_id': room_id,
                'banned_until': banned_until.isoformat() if banned_until else None
            })
        else:
            return jsonify({'error': 'user is not in the room'}), 404

    # Global ban (no room_id) — only superusers
    if not current_user.is_superuser:
        return jsonify({'error': 'not enough rights'}), 403

    # Mark user as banned globally
    user.is_banned = True
    user.ban_reason = ban_reason
    user.banned_at = datetime.utcnow()

    # Add IP to banned list if requested
    if ban_ip:
        user_ip = get_client_ip()
        if user.banned_ips:
            ips = [ip.strip() for ip in user.banned_ips.split(',') if ip.strip()]
        else:
            ips = []

        if user_ip not in ips:
            ips.append(user_ip)
            user.banned_ips = ','.join(ips)

    # Mark the user's memberships as 'banned' in all rooms (create RoomBan records)
    memberships = Member.query.filter_by(user_id=user_id).all()
    room_ids = [m.room_id for m in memberships]
    
    # Create RoomBan records for global ban
    for m in memberships:
        existing_ban = RoomBan.query.filter_by(user_id=user_id, room_id=m.room_id).first()
        if not existing_ban:
            room_ban = RoomBan(
                room_id=m.room_id,
                user_id=user_id,
                banned_by_id=current_user.id,
                reason=ban_reason,
                messages_deleted=data.get('delete_messages', False)
            )
            db.session.add(room_ban)
    
    # Delete all member records so servers don't appear in dashboard
    for m in memberships:
        db.session.delete(m)
    db.session.commit()

    # Optional deletion of all messages for global ban
    if data.get('delete_messages'):
        try:
            deleted = Message.query.filter(Message.user_id == user_id).delete(synchronize_session=False)
            db.session.commit()
            try:
                for rid in set(room_ids):
                    try:
                        socketio.emit('bulk_messages_deleted', {'user_id': user_id, 'room_id': rid, 'deleted': deleted}, room=str(rid))
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            db.session.rollback()

    # Notify affected rooms and the user
    try:
        target_room = f"user_{user_id}"
        print(f"[GLOBAL BAN] Banning user {user_id} globally to room {target_room}")
        
        for rid in set(room_ids):
            try:
                socketio.emit('member_removed', {'user_id': user_id, 'room_id': rid}, room=str(rid))
            except Exception:
                pass
        from flask import url_for
        socketio.emit('force_redirect', {'reason': 'banned', 'location': url_for('main.dashboard')}, room=target_room)
        # Also tell the user's client to remove these servers from their dashboard immediately
        try:
            for rid in set(room_ids):
                socketio.emit('server_removed', {'room_id': rid}, room=target_room)
        except Exception as e:
            print(f"[GLOBAL BAN] ERROR emitting server_removed: {e}")
            pass
        print(f"[GLOBAL BAN] All events emitted for user {user_id}")
    except Exception as e:
        print(f"[GLOBAL BAN] ERROR: {e}")
    except Exception as e:
        print(f"[GLOBAL BAN DEBUG] ERROR in emit block: {e}")
        pass

    return jsonify({
        'success': True,
        'message': f'user {user.username} is banned',
        'user_id': user_id,
        'reason': ban_reason
    })

@api_bp.route('/admin/user/<int:user_id>/unban', methods=['POST'])
@login_required
def unban_user(user_id):
    # Unban user by admin
    data = request.json or {}
    room_id = data.get('room_id')
    try:
        room_id = int(room_id) if room_id is not None and room_id != '' else None
    except Exception:
        room_id = None

    user = User.query.get_or_404(user_id)

    # If room_id provided, allow room owner/admins to unban within that room
    if room_id:
        admin_member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
        room = Room.query.get(room_id)
        allowed = False
        if current_user.is_superuser:
            allowed = True
        if room and room.owner_id == current_user.id:
            allowed = True
        if admin_member and admin_member.role in ['owner', 'admin']:
            allowed = True
        if not allowed:
            debug = {
                'current_user_id': current_user.id,
                'room_id': room_id,
                'room_owner_id': room.owner_id if room else None,
                'admin_member_role': admin_member.role if admin_member else None
            }
            return jsonify({'error': 'not enough rights no unban in this room', 'debug': debug}), 403

        # Delete the RoomBan record to unban
        room_bans = RoomBan.query.filter_by(user_id=user_id, room_id=room_id).all()
        if room_bans:
            for room_ban in room_bans:
                db.session.delete(room_ban)
            db.session.commit()
            return jsonify({'success': True, 'message': f'user {user.username} unbanned in room', 'room_id': room_id})
        return jsonify({'error': 'user is not banned in this room'}), 400

    # Global unban — only superusers
    if not current_user.is_superuser:
        return jsonify({'error': 'not enough rights'}), 403

    # Mark user as unbanned globally
    user.is_banned = False
    user.ban_reason = None
    user.banned_at = None
    user.banned_ips = ""

    # Unban globally - delete all RoomBan records for this user
    room_bans = RoomBan.query.filter_by(user_id=user_id).all()
    for room_ban in room_bans:
        db.session.delete(room_ban)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'user {user.username} is unbanned',
        'user_id': user_id
    })

@api_bp.route('/admin/user/<int:user_id>/change_password', methods=['POST'])
@login_required
def admin_change_password(user_id):
    # Admin can change user password
    if not current_user.is_superuser:
        return jsonify({'error': 'not enough rights'}), 403
    
    user = User.query.get_or_404(user_id)
    data = request.json
    new_password = data.get('password')
    
    from app.routes.auth import validate_password
    is_valid, error_message = validate_password(new_password)
    if not is_valid:
        return jsonify({'error': error_message}), 400
    
    user.password = generate_password_hash(new_password, method='scrypt')
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'password of user {user.username} is changed'
    })

# USER SETTINGS - Password change
@api_bp.route('/user/change_password', methods=['POST'])
@login_required
def change_password():
    # User changes their own password
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not old_password or not new_password:
        return jsonify({'error': 'fill in all fields'}), 400
    
    if not check_password_hash(current_user.password, old_password):
        return jsonify({'error': 'old password is wrong'}), 403
    
    if new_password != confirm_password:
        return jsonify({'error': 'passwords not matches'}), 400
    
    from app.routes.auth import validate_password
    is_valid, error_message = validate_password(new_password)
    if not is_valid:
        return jsonify({'error': error_message}), 400
    
    if new_password == old_password:
        return jsonify({'error': 'new password should differ from old'}), 400
    
    current_user.password = generate_password_hash(new_password, method='scrypt')
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'password changed successfully'
    })

@api_bp.route('/admin/banned_ips', methods=['GET'])
@login_required
def get_banned_ips():
    # Get list of all banned IPs
    if not current_user.is_superuser:
        return jsonify({'error': 'not enough rights'}), 403
    
    banned_users = User.query.filter_by(is_banned=True).all()
    banned_ips_list = {}
    
    for user in banned_users:
        if user.banned_ips:
            ips = [ip.strip() for ip in user.banned_ips.split(',') if ip.strip()]
            for ip in ips:
                if ip not in banned_ips_list:
                    banned_ips_list[ip] = []
                banned_ips_list[ip].append({
                    'username': user.username,
                    'user_id': user.id,
                    'reason': user.ban_reason,
                    'banned_at': user.banned_at.isoformat() if user.banned_at else None
                })
    
    return jsonify({
        'success': True,
        'banned_ips': banned_ips_list,
        'total_ips': len(banned_ips_list)
    })

@api_bp.route('/admin/user/<int:user_id>/kick_from_room/<int:room_id>', methods=['POST'])
@login_required
def kick_user_from_room(user_id, room_id):
    # Kick user from specific room
    # Check if requester is admin/owner of room
    try:
        room_id = int(room_id)
    except Exception:
        return jsonify({'error': 'wrong room_id'}), 400

    admin_member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    room = Room.query.get(room_id)
    allowed = False
    if current_user.is_superuser:
        allowed = True
    if room and has_room_permission(current_user.id, room, 'kick_members'):
        allowed = True
    if not allowed:
        debug = {
            'current_user_id': current_user.id,
            'room_id': room_id,
            'room_owner_id': room.owner_id if room else None,
            'admin_member_role': admin_member.role if admin_member else None
        }
        return jsonify({'error': 'not enough rights', 'debug': debug}), 403
    
    target_member = Member.query.filter_by(user_id=user_id, room_id=room_id).first()
    if not target_member:
        return jsonify({'error': 'user is not in the room'}), 404

    # Do not allow kicking a user who is marked as banned (ban should persist until unban)
    if target_member.role == 'banned':
        return jsonify({'error': 'the user is already banned, cannot kick'}), 400

    db.session.delete(target_member)
    db.session.commit()

    # Notify room and target user
    try:
        socketio.emit('member_removed', {'user_id': user_id, 'room_id': room_id}, room=str(room_id))
    except Exception:
        pass
    try:
        from flask import url_for
        socketio.emit('force_redirect', {'reason': 'kicked', 'location': url_for('main.dashboard')}, room=f"user_{user_id}")
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': f'user is kicked from the room'
    })


@api_bp.route('/admin/user/<int:user_id>/mute_in_room/<int:room_id>', methods=['POST'])
@login_required
def mute_user_in_room(user_id, room_id):
    try:
        room_id = int(room_id)
    except Exception:
        return jsonify({'error': 'wrong room_id'}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({'error': 'room is not found'}), 404
    if not has_room_permission(current_user.id, room, 'mute_members') and not current_user.is_superuser:
        return jsonify({'error': 'not enough rights'}), 403

    target_members = Member.query.filter_by(user_id=user_id, room_id=room_id).all()
    if not target_members:
        return jsonify({'error': 'user is not in the room'}), 404

    data = request.get_json(silent=True) or {}
    minutes = int(data.get('minutes') or 60)
    if minutes < 1:
        minutes = 1
    if minutes > 60 * 24 * 30:
        minutes = 60 * 24 * 30

    muted_until = datetime.utcnow() + timedelta(minutes=minutes)
    for target_member in target_members:
        target_member.muted_until = muted_until
    db.session.commit()
    try:
        socketio.emit('member_mute_updated', {
            'room_id': room_id,
            'user_id': user_id,
            'muted_until': muted_until.isoformat()
        }, room=str(room_id))
    except Exception:
        pass
    return jsonify({'success': True, 'muted_until': muted_until.isoformat()})


@api_bp.route('/admin/user/<int:user_id>/unmute_in_room/<int:room_id>', methods=['POST'])
@login_required
def unmute_user_in_room(user_id, room_id):
    try:
        room_id = int(room_id)
    except Exception:
        return jsonify({'error': 'wrong room_id'}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({'error': 'room is not found'}), 404
    if not has_room_permission(current_user.id, room, 'mute_members') and not current_user.is_superuser:
        return jsonify({'error': 'not enough rights'}), 403

    target_members = Member.query.filter_by(user_id=user_id, room_id=room_id).all()
    if not target_members:
        return jsonify({'error': 'user is not in the room'}), 404

    for target_member in target_members:
        target_member.muted_until = None
    db.session.commit()
    try:
        socketio.emit('member_mute_updated', {
            'room_id': room_id,
            'user_id': user_id,
            'muted_until': None
        }, room=str(room_id))
    except Exception:
        pass
    return jsonify({'success': True})


@api_bp.route('/admin/user/<int:user_id>/promote', methods=['POST'])
@login_required
def promote_user(user_id):
    # Promote a user to admin within a room. Expects JSON with room_id
    data = request.json or {}
    room_id = data.get('room_id')
    try:
        room_id = int(room_id) if room_id is not None and room_id != '' else None
    except Exception:
        room_id = None
    if not room_id:
        return jsonify({'error': 'room_id is not specified'}), 400
    # Requester must be owner/admin in that room or superuser
    admin_member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    room = Room.query.get(room_id)
    allowed = False
    if current_user.is_superuser:
        allowed = True
    if room and room.owner_id == current_user.id:
        allowed = True
    if admin_member and admin_member.role in ['owner', 'admin']:
        allowed = True
    if not allowed:
        debug = {
            'current_user_id': current_user.id,
            'room_id': room_id,
            'room_owner_id': room.owner_id if room else None,
            'admin_member_role': admin_member.role if admin_member else None
        }
        return jsonify({'error': 'not enough rights', 'debug': debug}), 403

    target_member = Member.query.filter_by(user_id=user_id, room_id=room_id).first()
    if not target_member:
        return jsonify({'error': 'user is not in the room'}), 404

    # Prevent promoting owner away or no-op if already admin
    if target_member.role == 'owner':
        return jsonify({'error': 'cannot change the owners role'}), 400

    target_member.role = 'admin'
    ensure_default_roles(room_id)
    ensure_user_default_roles(user_id, room_id)
    db.session.commit()

    return jsonify({'success': True, 'message': 'user promoted to admin'})


@api_bp.route('/admin/user/<int:user_id>/demote', methods=['POST'])
@login_required
def demote_user(user_id):
    # Demote an admin back to member within a room. Expects JSON with room_id
    data = request.json or {}
    room_id = data.get('room_id')
    try:
        room_id = int(room_id) if room_id is not None and room_id != '' else None
    except Exception:
        room_id = None
    if not room_id:
        return jsonify({'error': 'room_id is not specified'}), 400

    # Only room creator (owner) or superuser can demote
    room = Room.query.get(room_id)
    allowed = False
    if current_user.is_superuser:
        allowed = True
    if room and room.owner_id == current_user.id:
        allowed = True
    if not allowed:
        admin_member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
        debug = {
            'current_user_id': current_user.id,
            'room_id': room_id,
            'room_owner_id': room.owner_id if room else None,
            'admin_member_role': admin_member.role if admin_member else None
        }
        return jsonify({'error': 'not enough rights', 'debug': debug}), 403

    target_member = Member.query.filter_by(user_id=user_id, room_id=room_id).first()
    if not target_member:
        return jsonify({'error': 'user is not in the room'}), 404

    if target_member.role == 'owner':
        return jsonify({'error': 'cannot change the owners role'}), 400

    if target_member.role != 'admin':
        return jsonify({'error': 'user is not an admin'}), 400

    target_member.role = 'member'
    admin_role = Role.query.filter_by(room_id=room_id, mention_tag='admin').first()
    if admin_role:
        links = MemberRole.query.filter_by(room_id=room_id, user_id=user_id, role_id=admin_role.id).all()
        for link in links:
            db.session.delete(link)
    db.session.commit()

    return jsonify({'success': True, 'message': 'user is demoted to member'})


@api_bp.route('/admin/user/<int:user_id>/delete_messages', methods=['POST'])
@login_required
def delete_user_messages(user_id):
    # Delete all messages from a user in a specific room (owner/admin allowed). Expects JSON {room_id}
    # Emits a `bulk_messages_deleted` socket event for the room with user_id
    data = request.json or {}
    room_id = data.get('room_id')
    try:
        room_id = int(room_id) if room_id is not None and room_id != '' else None
    except Exception:
        room_id = None
    if not room_id:
        return jsonify({'error': 'room_id is not specified'}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({'error': 'room is not found'}), 404

    admin_member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    allowed = False
    if current_user.is_superuser:
        allowed = True
    if room and room.owner_id == current_user.id:
        allowed = True
    if admin_member and admin_member.role in ['owner', 'admin']:
        allowed = True
    if not allowed:
        debug = {
            'current_user_id': current_user.id,
            'room_id': room_id,
            'room_owner_id': room.owner_id if room else None,
            'admin_member_role': admin_member.role if admin_member else None
        }
        return jsonify({'error': 'not enough rights', 'debug': debug}), 403

    # collect channel ids for the room
    channel_ids = [c.id for c in room.channels]
    if not channel_ids:
        return jsonify({'success': True, 'deleted': 0})

    # delete messages from these channels by user
    deleted = Message.query.filter(Message.user_id == user_id, Message.channel_id.in_(channel_ids)).delete(synchronize_session=False)
    db.session.commit()

    # Notify room listeners that messages from this user were removed
    socketio.emit('bulk_messages_deleted', {'user_id': user_id, 'room_id': room_id, 'deleted': deleted}, room=str(room_id))

    return jsonify({'success': True, 'deleted': deleted, 'room_id': room_id})
