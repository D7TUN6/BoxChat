"""
Content-related models: messages, reactions, stickers
"""
from datetime import datetime
from app.extensions import db


class Message(db.Model):
    """Chat message"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=False)
    
    # Message content type
    message_type = db.Column(db.String(20), default='text')  # 'text', 'image', 'file', 'music', 'sticker'
    file_url = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(200), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    # Reply target (self-referential FK to another message)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    
    # Relationships
    user = db.relationship('User', backref='messages')
    reactions = db.relationship('MessageReaction', backref='message', lazy=True, cascade='all, delete-orphan')


class MessageReaction(db.Model):
    """Message reactions (emojis and stickers)"""
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    emoji = db.Column(db.String(50), nullable=False)
    reaction_type = db.Column(db.String(20), default='emoji')  # 'emoji' or 'sticker'
    
    # Relationships
    user = db.relationship('User', backref='reactions')


class ReadMessage(db.Model):
    """Track read messages in channels"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=False)
    last_read_message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    last_read_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='read_messages')
    channel = db.relationship('Channel', backref='read_by_users')


class StickerPack(db.Model):
    """Collection of stickers"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon_emoji = db.Column(db.String(10), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    owner = db.relationship('User', backref='sticker_packs')
    stickers = db.relationship('Sticker', backref='pack', lazy=True, cascade='all, delete-orphan')


class Sticker(db.Model):
    """Individual sticker"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    pack_id = db.Column(db.Integer, db.ForeignKey('sticker_pack.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    owner = db.relationship('User', backref='stickers')
