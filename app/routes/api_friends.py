from datetime import datetime

from flask import request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, func

from app.extensions import db, socketio
from app.models import User, Room, Channel, Member


def _friendship_pair(a_id, b_id):
    low = min(int(a_id), int(b_id))
    high = max(int(a_id), int(b_id))
    return low, high


def _are_friends(a_id, b_id):
    from app.models import Friendship

    low, high = _friendship_pair(a_id, b_id)
    return Friendship.query.filter_by(user_low_id=low, user_high_id=high).first() is not None


def register_friends_routes(api_bp):
    @api_bp.route('/api/v1/friends/status/<int:user_id>', methods=['GET'])
    @login_required
    def friend_status(user_id):
        from app.models import FriendRequest

        target = User.query.get_or_404(user_id)
        if target.id == current_user.id:
            return jsonify({'success': True, 'status': 'self'})

        if _are_friends(current_user.id, target.id):
            return jsonify({'success': True, 'status': 'friends'})

        pending = FriendRequest.query.filter(
            FriendRequest.status == 'pending',
            or_(
                and_(FriendRequest.from_user_id == current_user.id, FriendRequest.to_user_id == target.id),
                and_(FriendRequest.from_user_id == target.id, FriendRequest.to_user_id == current_user.id),
            )
        ).order_by(FriendRequest.id.desc()).first()
        if pending:
            direction = 'incoming' if pending.to_user_id == current_user.id else 'outgoing'
            return jsonify({
                'success': True,
                'status': 'pending',
                'direction': direction,
                'request_id': pending.id,
            })

        return jsonify({'success': True, 'status': 'none'})

    @api_bp.route('/api/v1/friends/request', methods=['POST'])
    @login_required
    def send_friend_request():
        from app.models import FriendRequest, Friendship

        data = request.get_json(silent=True) or {}
        username = str(data.get('username') or '').strip()
        if not username:
            return jsonify({'error': 'username is required'}), 400

        target = User.query.filter(func.lower(User.username) == username.lower()).first()
        if not target:
            return jsonify({'error': 'user not found'}), 404
        if target.id == current_user.id:
            return jsonify({'error': 'cannot add yourself'}), 400

        low, high = _friendship_pair(current_user.id, target.id)
        if Friendship.query.filter_by(user_low_id=low, user_high_id=high).first():
            return jsonify({'success': True, 'status': 'already_friends'}), 200

        pending = FriendRequest.query.filter(
            FriendRequest.status == 'pending',
            or_(
                and_(FriendRequest.from_user_id == current_user.id, FriendRequest.to_user_id == target.id),
                and_(FriendRequest.from_user_id == target.id, FriendRequest.to_user_id == current_user.id),
            )
        ).first()
        if pending:
            try:
                print(f"[FRIEND REQUEST] Pending already exists between {current_user.id} and {target.id}")
            except Exception:
                pass
            return jsonify({'success': True, 'status': 'pending'}), 200

        fr = FriendRequest(from_user_id=current_user.id, to_user_id=target.id, status='pending')
        db.session.add(fr)
        db.session.commit()
        try:
            print(f"[FRIEND REQUEST] Emitting friend_request_received to user_{target.id} request_id={fr.id}")
        except Exception:
            pass
        socketio.emit('friend_request_received', {
            'request_id': fr.id,
            'from_user_id': current_user.id,
            'from_username': current_user.username,
        }, room=f"user_{target.id}")
        return jsonify({'success': True, 'status': 'sent', 'request_id': fr.id})

    @api_bp.route('/api/v1/friends/requests', methods=['GET'])
    @login_required
    def list_friend_requests():
        from app.models import FriendRequest

        incoming = FriendRequest.query.filter_by(to_user_id=current_user.id, status='pending').order_by(FriendRequest.id.desc()).limit(50).all()
        outgoing = FriendRequest.query.filter_by(from_user_id=current_user.id, status='pending').order_by(FriendRequest.id.desc()).limit(50).all()

        def _serialize(fr):
            other_id = fr.from_user_id if fr.to_user_id == current_user.id else fr.to_user_id
            other = User.query.get(other_id)
            return {
                'id': fr.id,
                'status': fr.status,
                'created_at': fr.created_at.isoformat() if fr.created_at else None,
                'direction': 'incoming' if fr.to_user_id == current_user.id else 'outgoing',
                'user': {
                    'id': other.id if other else other_id,
                    'username': other.username if other else 'unknown',
                    'avatar_url': (other.avatar_url or 'https://placehold.co/50x50') if other else 'https://placehold.co/50x50',
                }
            }

        return jsonify({
            'incoming': [_serialize(fr) for fr in incoming],
            'outgoing': [_serialize(fr) for fr in outgoing],
        })

    @api_bp.route('/api/v1/friends/requests/<int:request_id>/respond', methods=['POST'])
    @login_required
    def respond_friend_request(request_id):
        from app.models import FriendRequest, Friendship
        from app.functions import ensure_default_roles, ensure_user_default_roles

        fr = FriendRequest.query.get_or_404(request_id)
        if fr.to_user_id != current_user.id:
            return jsonify({'error': 'Access denied'}), 403
        if fr.status != 'pending':
            return jsonify({'error': 'request is not pending'}), 400

        data = request.get_json(silent=True) or {}
        action = str(data.get('action') or '').strip().lower()
        if action not in {'accept', 'decline'}:
            return jsonify({'error': 'action must be accept or decline'}), 400

        now = datetime.utcnow()
        if action == 'decline':
            fr.status = 'declined'
            fr.responded_at = now
            db.session.commit()
            socketio.emit('friend_request_updated', {
                'request_id': fr.id,
                'status': 'declined',
                'by_user_id': current_user.id,
                'by_username': current_user.username,
            }, room=f"user_{fr.from_user_id}")
            return jsonify({'success': True, 'status': 'declined'})

        low, high = _friendship_pair(fr.from_user_id, fr.to_user_id)
        existing = Friendship.query.filter_by(user_low_id=low, user_high_id=high).first()
        if not existing:
            db.session.add(Friendship(user_low_id=low, user_high_id=high))

        # Auto-create DM on accept so it appears immediately in dashboard/sidebar.
        existing_dm = Room.query.filter(
            Room.type == 'dm',
            Room.members.any(Member.user_id == fr.from_user_id),
            Room.members.any(Member.user_id == fr.to_user_id)
        ).first()
        dm_room_id = None
        if existing_dm:
            dm_room_id = existing_dm.id
        else:
            from_user = User.query.get(fr.from_user_id)
            to_user = User.query.get(fr.to_user_id)
            dm = Room(
                name=f"DM: {(from_user.username if from_user else fr.from_user_id)} - {(to_user.username if to_user else fr.to_user_id)}",
                type='dm'
            )
            db.session.add(dm)
            db.session.flush()
            for uid in [fr.from_user_id, fr.to_user_id]:
                db.session.add(Member(user_id=uid, room_id=dm.id, role='owner'))
            db.session.add(Channel(room_id=dm.id, name='general', icon_emoji='💬'))
            db.session.flush()
            ensure_default_roles(dm.id)
            ensure_user_default_roles(fr.from_user_id, dm.id)
            ensure_user_default_roles(fr.to_user_id, dm.id)
            dm_room_id = dm.id

        fr.status = 'accepted'
        fr.responded_at = now
        db.session.commit()
        socketio.emit('friend_request_updated', {
            'request_id': fr.id,
            'status': 'accepted',
            'by_user_id': current_user.id,
            'by_username': current_user.username,
            'dm_room_id': dm_room_id,
        }, room=f"user_{fr.from_user_id}")
        return jsonify({'success': True, 'status': 'accepted', 'dm_room_id': dm_room_id})

    @api_bp.route('/api/v1/dm/<int:user_id>/create', methods=['POST'])
    @login_required
    def create_dm(user_id):
        from app.functions import ensure_default_roles, ensure_user_default_roles

        user = User.query.get_or_404(user_id)

        if not _are_friends(current_user.id, user_id):
            return jsonify({'error': 'You can only start DMs with friends'}), 403

        existing_dm = Room.query.filter(
            Room.type == 'dm',
            Room.members.any(Member.user_id == current_user.id),
            Room.members.any(Member.user_id == user_id)
        ).first()

        if existing_dm:
            return jsonify({'success': True, 'room_id': existing_dm.id})

        dm = Room(name=f"DM: {current_user.username} - {user.username}", type='dm')
        db.session.add(dm)
        db.session.flush()

        for uid in [current_user.id, user_id]:
            member = Member(user_id=uid, room_id=dm.id, role='owner')
            db.session.add(member)

        channel = Channel(room_id=dm.id, name='general', icon_emoji='💬')
        db.session.add(channel)
        db.session.commit()

        ensure_default_roles(dm.id)
        ensure_user_default_roles(current_user.id, dm.id)
        ensure_user_default_roles(user_id, dm.id)
        db.session.commit()

        return jsonify({'success': True, 'room_id': dm.id})
