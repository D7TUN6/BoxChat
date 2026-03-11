from flask import request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models import Room, Member


def register_search_routes(api_bp):
    @api_bp.route('/api/v1/search/users', methods=['GET'])
    @login_required
    def search_users():
        return jsonify({'error': 'User search is disabled'}), 410

    @api_bp.route('/api/v1/search/servers', methods=['GET'])
    @login_required
    def search_servers():
        query = request.args.get('q', '', type=str).strip()
        member_counts = (
            db.session.query(Member.room_id.label('room_id'), func.count(Member.id).label('cnt'))
            .group_by(Member.room_id)
            .subquery()
        )
        rooms_query = (
            db.session.query(Room, func.coalesce(member_counts.c.cnt, 0).label('member_count'))
            .outerjoin(member_counts, member_counts.c.room_id == Room.id)
            .filter(Room.type != 'dm', Room.is_public.is_(True))
        )
        if query:
            rooms_query = rooms_query.filter(Room.name.ilike(f'%{query}%'))

        rows = rooms_query.order_by(Room.name.asc()).limit(20).all()

        rooms_data = [{
            'id': r.id,
            'name': r.name,
            'description': getattr(r, 'description', None) or '',
            'type': r.type,
            'avatar_url': r.avatar_url or 'https://placehold.co/100x100',
            'member_count': int(member_count or 0)
        } for r, member_count in rows]

        return jsonify({'servers': rooms_data})
