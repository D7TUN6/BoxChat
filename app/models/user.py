"""
User-related models
"""
from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class User(UserMixin, db.Model):
    """User model with profile and privacy settings"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    
    # Profile info
    bio = db.Column(db.String(300), default="")
    avatar_url = db.Column(db.String(300), default="https://via.placeholder.com/50")
    birth_date = db.Column(db.String(20))
    
    # Privacy settings
    privacy_searchable = db.Column(db.Boolean, default=True)  # Can be found in search
    privacy_listable = db.Column(db.Boolean, default=True)    # Visible in user list
    # Presence/status
    presence_status = db.Column(db.String(20), default='offline')  # 'online','offline','away','hidden'
    last_seen = db.Column(db.DateTime, nullable=True)
    hide_status = db.Column(db.Boolean, default=False)
    
    # Permissions
    is_superuser = db.Column(db.Boolean, default=False)
    
    # Relationships
    music_tracks = db.relationship('UserMusic', backref='user', lazy=True, cascade='all, delete-orphan')
    memberships = db.relationship('Member', backref='user', lazy=True)


class UserMusic(db.Model):
    """User's music library"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=True)
    file_url = db.Column(db.String(500), nullable=False)
    cover_url = db.Column(db.String(500), nullable=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
