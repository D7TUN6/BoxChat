# Chat-related models: rooms, channels, members
from app.extensions import db

class Room(db.Model):
    # Chat room (server, DM, or broadcast)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    type = db.Column(db.String(20), nullable=False)  # 'dm', 'server', 'broadcast'
    is_public = db.Column(db.Boolean, default=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    description = db.Column(db.String(500), nullable=True)
    avatar_url = db.Column(db.String(300), nullable=True)
    banner_url = db.Column(db.String(300), nullable=True)
    invite_token = db.Column(db.String(100), nullable=True, unique=True)
    
    # For blogs: linked chat for comments (not implemented yet, but reserved for future use)
    linked_chat_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    
    # Relationships
    channels = db.relationship('Channel', backref='room', lazy=True, cascade='all, delete-orphan')
    members = db.relationship('Member', backref='room', lazy=True, cascade='all, delete-orphan')

class Channel(db.Model):
    # Channel within a room
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    icon_emoji = db.Column(db.String(10), nullable=True)
    icon_image_url = db.Column(db.String(300), nullable=True)
    writer_role_ids_json = db.Column(db.Text, nullable=True)  # JSON array of role ids allowed to write
    
    # Relationships
    messages = db.relationship('Message', backref='channel', lazy=True, cascade='all, delete-orphan')

class Member(db.Model):
    # Room membership
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(20), default='member')  # 'owner', 'admin', 'member'
    muted_until = db.Column(db.DateTime, nullable=True)


class Role(db.Model):
    # Per-room role used for mentions and permissions
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    mention_tag = db.Column(db.String(60), nullable=False)  # normalized token used in @tag
    is_system = db.Column(db.Boolean, default=False)  # e.g. everyone/admin
    can_be_mentioned_by_everyone = db.Column(db.Boolean, default=False)
    permissions_json = db.Column(db.Text, nullable=True)  # JSON array of permission keys
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    room = db.relationship('Room', backref=db.backref('roles', lazy=True, cascade='all, delete-orphan'))


class MemberRole(db.Model):
    # Mapping user -> role within room
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id', ondelete='CASCADE'), nullable=False, index=True)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id', ondelete='CASCADE'), nullable=False, index=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    user = db.relationship('User', backref=db.backref('member_roles', lazy=True, cascade='all, delete-orphan'))
    role = db.relationship('Role', backref=db.backref('member_links', lazy=True, cascade='all, delete-orphan'))


class RoleMentionPermission(db.Model):
    # Which source role can mention which target role
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id', ondelete='CASCADE'), nullable=False, index=True)
    source_role_id = db.Column(db.Integer, db.ForeignKey('role.id', ondelete='CASCADE'), nullable=False, index=True)
    target_role_id = db.Column(db.Integer, db.ForeignKey('role.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    source_role = db.relationship('Role', foreign_keys=[source_role_id], backref='can_mention')
    target_role = db.relationship('Role', foreign_keys=[target_role_id], backref='mentionable_by')

class RoomBan(db.Model):
    # Room ban record (separate from membership)
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    banned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    reason = db.Column(db.String(500), nullable=True)
    banned_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    banned_until = db.Column(db.DateTime, nullable=True)
    messages_deleted = db.Column(db.Boolean, default=False)
    
    # Relationships
    room = db.relationship('Room', foreign_keys=[room_id])
    user = db.relationship('User', foreign_keys=[user_id])
    banned_by = db.relationship('User', foreign_keys=[banned_by_id])
