"""
Main routes (dashboard, explore, rooms)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from app.extensions import db, socketio
from app.models import Room, Channel, Member, Message, ReadMessage, User

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def dashboard():
    """Main dashboard - shows DMs and servers"""
    # Get DMs with unread count
    dms_query = db.session.query(Room, Member).join(Member).filter(
        Member.user_id == current_user.id, 
        Room.type == 'dm'
    ).all()
    
    dms_with_info = []
    for room, member in dms_query:
        # Find other member
        other_member = Member.query.filter(
            Member.room_id == room.id,
            Member.user_id != current_user.id
        ).first()
        other_user = other_member.user if other_member else None
        
        # Get DM channel and unread count
        channel = Channel.query.filter_by(room_id=room.id).first()
        unread_count = 0
        
        if channel:
            read_msg = ReadMessage.query.filter_by(
                user_id=current_user.id,
                channel_id=channel.id
            ).first()
            
            if read_msg and read_msg.last_read_message_id:
                unread_count = Message.query.filter(
                    Message.channel_id == channel.id,
                    Message.id > read_msg.last_read_message_id,
                    Message.user_id != current_user.id
                ).count()
            elif not read_msg:
                unread_count = Message.query.filter(
                    Message.channel_id == channel.id,
                    Message.user_id != current_user.id
                ).count()
        
        dms_with_info.append({
            'room': room,
            'other_user': other_user,
            'unread_count': unread_count
        })
    
    # Sort by unread count, then by ID
    dms_with_info.sort(key=lambda x: (
        x['unread_count'] == 0,
        -x['room'].id
    ))
    
    # Get servers/channels with roles
    servers_query = db.session.query(Room, Member).join(Member).filter(
        Member.user_id == current_user.id, 
        Room.type.in_(['server', 'broadcast'])
    ).all()
    
    servers_with_role = []
    for room, member in servers_query:
        if room:
            servers_with_role.append({
                'room': room,
                'role': member.role
            })
    
    # Clean orphaned members
    orphaned_members = db.session.query(Member).filter(
        Member.user_id == current_user.id,
        ~Member.room_id.in_(db.session.query(Room.id))
    ).all()
    if orphaned_members:
        for orphan in orphaned_members:
            db.session.delete(orphan)
        db.session.commit()
    
    return render_template('dashboard.html', dms=dms_with_info, servers=servers_with_role, user=current_user)


@main_bp.route('/explore')
@login_required
def explore():
    """Explore public rooms and users"""
    query = request.args.get('q', '')
    users = []
    rooms = []
    
    if query:
        users = User.query.filter(
            User.username.contains(query),
            User.privacy_searchable == True
        ).all()
        rooms = Room.query.filter(
            Room.name.contains(query),
            Room.is_public == True
        ).all()
    else:
        if current_user.is_superuser:
            users = User.query.all()
        else:
            users = User.query.filter_by(privacy_listable=True).all()
        rooms = Room.query.filter_by(is_public=True).all()
    
    return render_template('explore.html', users=users, rooms=rooms, query=query)


@main_bp.route('/create_room', methods=['POST'])
@login_required
def create_room():
    """Create new room/server"""
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
    
    return redirect(url_for('main.view_room', room_id=new_room.id))


@main_bp.route('/start_dm/<int:user_id>')
@login_required
def start_dm(user_id):
    """Start direct message with user"""
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
    
    # Notify other user via Socket.IO
    socketio.emit('new_dm_created', {
        'room_id': room.id,
        'from_user': current_user.username,
        'from_user_id': current_user.id,
        'from_avatar': current_user.avatar_url
    }, room=f"user_{other.id}")
    
    return redirect(url_for('main.view_room', room_id=room.id))


@main_bp.route('/room/<int:room_id>')
@login_required
def view_room(room_id):
    """View room and messages"""
    room = Room.query.get_or_404(room_id)
    member = Member.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    
    if not member or member.role == 'banned':
        if not (room.is_public and not member):
            flash('Нет доступа или вы забанены')
            return redirect(url_for('main.dashboard'))
    
    # Get active channel
    active_channel_id = request.args.get('channel_id')
    if not active_channel_id and room.channels:
        active_channel_id = room.channels[0].id
    
    messages = []
    if active_channel_id:
        messages = Message.query.filter_by(channel_id=active_channel_id).order_by(Message.timestamp.asc()).all()
        
        # Load reactions for each message
        for msg in messages:
            msg.reactions_grouped = {}
            reactions = Message.query.filter_by(id=msg.id).first().reactions
            for reaction in reactions:
                if reaction.emoji not in msg.reactions_grouped:
                    msg.reactions_grouped[reaction.emoji] = []
                msg.reactions_grouped[reaction.emoji].append(reaction.user.username)
            # If this message is a reply to another persisted message, include reply metadata
            try:
                if getattr(msg, 'reply_to_id', None):
                    orig = Message.query.get(msg.reply_to_id)
                    if orig:
                        # build a small snippet (first line) for display
                        snippet = (orig.content or '').split('\n')[0][:200]
                        msg.reply_to = {
                            'id': orig.id,
                            'username': orig.user.username if orig.user else 'Unknown',
                            'snippet': snippet
                        }
            except Exception:
                msg.reply_to = None
        
        # Mark messages as read
        if messages:
            last_message = messages[-1]
            read_msg = ReadMessage.query.filter_by(
                user_id=current_user.id,
                channel_id=active_channel_id
            ).first()
            
            if read_msg:
                read_msg.last_read_message_id = last_message.id
                read_msg.last_read_at = datetime.utcnow()
            else:
                read_msg = ReadMessage(
                    user_id=current_user.id,
                    channel_id=active_channel_id,
                    last_read_message_id=last_message.id
                )
                db.session.add(read_msg)
            
            db.session.commit()
            
            # Notify others about read status
            socketio.emit('read_status_updated', {
                'user_id': current_user.id,
                'username': current_user.username,
                'channel_id': active_channel_id
            }, room=str(active_channel_id))
    
    return render_template(
        'room.html',
        room=room,
        member=member,
        active_channel_id=int(active_channel_id) if active_channel_id else None,
        active_channel=Channel.query.get(active_channel_id) if active_channel_id else None,
        messages=messages,
        channel_unread_counts={
            ch.id: (
                Message.query.filter(
                    Message.channel_id == ch.id,
                    Message.user_id != current_user.id,
                    Message.id > (ReadMessage.query.filter_by(user_id=current_user.id, channel_id=ch.id).first().last_read_message_id if ReadMessage.query.filter_by(user_id=current_user.id, channel_id=ch.id).first() and ReadMessage.query.filter_by(user_id=current_user.id, channel_id=ch.id).first().last_read_message_id else 0)
                ).count()
            ) for ch in room.channels
        }
    )


@main_bp.route('/join_room/<int:room_id>')
@login_required
def join_room_view(room_id):
    """Join public room"""
    room = Room.query.get_or_404(room_id)
    
    if room.is_public:
        if not Member.query.filter_by(user_id=current_user.id, room_id=room_id).first():
            m = Member(user_id=current_user.id, room_id=room_id, role='member')
            db.session.add(m)
            db.session.commit()
    
    return redirect(url_for('main.view_room', room_id=room_id))


@main_bp.route('/join/invite/<token>')
@login_required
def join_room_by_invite(token):
    """Join room by invite token"""
    room = Room.query.filter_by(invite_token=token).first_or_404()
    
    # Check if user is already a member
    if not Member.query.filter_by(user_id=current_user.id, room_id=room.id).first():
        m = Member(user_id=current_user.id, room_id=room.id, role='member')
        db.session.add(m)
        db.session.commit()
    
    return redirect(url_for('main.view_room', room_id=room.id))


@main_bp.route('/profile/<int:user_id>')
@login_required
def view_profile(user_id):
    """View user profile"""
    user = User.query.get_or_404(user_id)
    return render_template('profile_preview.html', profile_user=user, current_user=current_user)
