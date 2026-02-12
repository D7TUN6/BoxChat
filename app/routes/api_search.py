from flask import request, jsonify
from flask_login import login_required, current_user

from app.models import Room


def register_search_routes(api_bp):
    @api_bp.route('/api/v1/search/users', methods=['GET'])
    @login_required
    def search_users():
        return jsonify({'error': 'User search is disabled'}), 410

    @api_bp.route('/api/v1/search/servers', methods=['GET'])
    @login_required
    def search_servers():
        query = request.args.get('q', '', type=str).strip()
        rooms_query = Room.query.filter(
            Room.type != 'dm',
            (Room.is_public == True)
        )
        if query:
            rooms_query = rooms_query.filter(Room.name.ilike(f'%{query}%'))

        rooms = rooms_query.order_by(Room.name.asc()).limit(20).all()

        rooms_data = [{
            'id': r.id,
            'name': r.name,
            'description': getattr(r, 'description', None) or '',
            'type': r.type,
            'avatar_url': r.avatar_url or 'https://placehold.co/100x100',
            'member_count': len(r.members)
        } for r in rooms]

        return jsonify({'servers': rooms_data})
