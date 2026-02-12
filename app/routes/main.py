# Main routes (dashboard, explore, rooms)

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from app.extensions import db, socketio
from app.models import Room, Channel, Member, Message, ReadMessage, User, RoomBan
from app.routes.spa import send_spa_index
from app.functions import ensure_default_roles, ensure_user_default_roles

main_bp = Blueprint('main', __name__)


def _get_active_room_ban(user_id: int, room_id: int):
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

@main_bp.route('/')
@login_required
def dashboard():
    # Main dashboard - shows DMs and servers
    return send_spa_index()

@main_bp.route('/explore')
@login_required
def explore():
    # Explore public rooms and users
    return send_spa_index()

@main_bp.route('/room/<int:room_id>')
@login_required
def view_room(room_id):
    # View room and messages
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    room_ban = _get_active_room_ban(current_user.id, room_id)
    if room_ban:
        flash(f'you are banned from this room{": " + room_ban.reason if room_ban.reason else ""}')
        return redirect(url_for('main.dashboard'))
    
    if not member:
        if not room.is_public:
            flash('Нет доступа к этой комнате')
            return redirect(url_for('main.dashboard'))

    return send_spa_index()

@main_bp.route('/profile/<int:user_id>')
@login_required
def view_profile(user_id):
    return send_spa_index()

@main_bp.route('/create_room', methods=['POST'])
@login_required
def create_room():
    # Create new room/server
    name = request.form.get('name')
    rtype = request.form.get('type')  # server, broadcast
    is_public = 'is_public' in request.form
    
    new_room = Room(name=name, type=rtype, is_public=is_public, owner_id=current_user.id)
    db.session.add(new_room)
    db.session.commit()
    
    # Add creator as owner
    mem = Member(user_id=current_user.id, room_id=new_room.id, role='owner')
    # Create default #general channel
    chan = Channel(name='general', room_id=new_room.id)
    
    db.session.add(mem)
    db.session.add(chan)
    db.session.commit()

    ensure_default_roles(new_room.id)
    ensure_user_default_roles(current_user.id, new_room.id)
    db.session.commit()
    
    return redirect(url_for('main.view_room', room_id=new_room.id))

@main_bp.route('/start_dm/<int:user_id>')
@login_required
def start_dm(user_id):
    # Start direct message with user
    other = User.query.get_or_404(user_id)
    
    # Check if DM already exists
    existing_dm = db.session.query(Room).join(Member).filter(
        Room.type == 'dm',
        Member.user_id.in_([current_user.id, other.id])
    ).group_by(Room.id).having(
        db.func.count(db.distinct(Member.user_id)) == 2
    ).first()
    
    if existing_dm:
        return redirect(url_for('main.view_room', room_id=existing_dm.id))
    
    # Create new DM
    room = Room(name=f"dm_{current_user.id}_{other.id}", type='dm', is_public=False)
    db.session.add(room)
    db.session.commit()
    
    m1 = Member(user_id=current_user.id, room_id=room.id, role='admin')
    m2 = Member(user_id=other.id, room_id=room.id, role='admin')
    c1 = Channel(name='main', room_id=room.id)
    
    db.session.add_all([m1, m2, c1])
    db.session.commit()

    ensure_default_roles(room.id)
    ensure_user_default_roles(current_user.id, room.id)
    ensure_user_default_roles(other.id, room.id)
    db.session.commit()
    
    # Notify other user via Socket.IO
    socketio.emit('new_dm_created', {
        'room_id': room.id,
        'from_user': current_user.username,
        'from_user_id': current_user.id,
        'from_avatar': current_user.avatar_url
    }, room=f"user_{other.id}")
    
    return redirect(url_for('main.view_room', room_id=room.id))

@main_bp.route('/join_room/<int:room_id>')
@login_required
def join_room_view(room_id):
    # Join public room
    room = Room.query.get_or_404(room_id)
    # Block globally banned users from joining
    if getattr(current_user, 'is_banned', False):
        flash('your account is banned and cannot join rooms')
        return redirect(url_for('main.dashboard'))
    # Check if user is banned from this room
    room_ban = _get_active_room_ban(current_user.id, room_id)
    if room_ban:
        flash(f'you are banned from this room{": " + room_ban.reason if room_ban.reason else ""}')
        return redirect(url_for('main.dashboard'))
    
    # Check if user already has membership
    existing = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    if room.is_public:
        if not existing:
            m = Member(user_id=current_user.id, room_id=room_id, role='member')
            db.session.add(m)
            db.session.commit()
            ensure_default_roles(room_id)
            ensure_user_default_roles(current_user.id, room_id)
            db.session.commit()
    
    return redirect(url_for('main.view_room', room_id=room_id))

@main_bp.route('/join/invite/<token>')
@login_required
def join_room_by_invite(token):
    # Join room by invite token
    room = Room.query.filter_by(invite_token=token).first_or_404()
    # Block globally banned users
    if getattr(current_user, 'is_banned', False):
        flash('your account is banned and cannot join rooms')
        return redirect(url_for('main.dashboard'))

    # Check if user is banned from this room
    room_ban = _get_active_room_ban(current_user.id, room.id)
    if room_ban:
        flash(f'you are banned from this room{": " + room_ban.reason if room_ban.reason else ""}')
        return redirect(url_for('main.dashboard'))

    # Check if user is already a member
    existing = Member.query.filter_by(user_id=current_user.id, room_id=room.id).first()
    if not existing:
        m = Member(user_id=current_user.id, room_id=room.id, role='member')
        db.session.add(m)
        db.session.commit()
        ensure_default_roles(room.id)
        ensure_user_default_roles(current_user.id, room.id)
        db.session.commit()
    
    return redirect(url_for('main.view_room', room_id=room.id))
