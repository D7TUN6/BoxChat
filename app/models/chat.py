"""
Chat-related models: rooms, channels, members
"""
from app.extensions import db


class Room(db.Model):
    """Chat room (server, DM, or broadcast)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    type = db.Column(db.String(20), nullable=False)  # 'dm', 'server', 'broadcast'
    is_public = db.Column(db.Boolean, default=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    avatar_url = db.Column(db.String(300), nullable=True)
    invite_token = db.Column(db.String(100), nullable=True, unique=True)
    
    # For blogs: linked chat for comments
    linked_chat_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    
    # Relationships
    channels = db.relationship('Channel', backref='room', lazy=True, cascade='all, delete-orphan')
    members = db.relationship('Member', backref='room', lazy=True, cascade='all, delete-orphan')


class Channel(db.Model):
    """Channel within a room"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    icon_emoji = db.Column(db.String(10), nullable=True)
    icon_image_url = db.Column(db.String(300), nullable=True)
    
    # Relationships
    messages = db.relationship('Message', backref='channel', lazy=True, cascade='all, delete-orphan')


class Member(db.Model):
    """Room membership"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(20), default='member')  # 'owner', 'admin', 'member', 'banned'
