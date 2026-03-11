# Authentication routes

from datetime import datetime, timedelta
import os
import sqlite3
from flask import Blueprint, request, redirect, url_for, flash, jsonify, session, current_app
from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from app.extensions import db
from app.models import User, AuthThrottle
from app.routes.spa import send_spa_index
from app.utils.ip import get_client_ip as _get_client_ip
import re

auth_bp = Blueprint('auth', __name__)
DUMMY_PASSWORD_HASH = generate_password_hash('not_the_real_password_123!', method='scrypt')
MAX_FAILED_LOGIN_ATTEMPTS = 5
MAX_FAILED_IP_ATTEMPTS = 15
LOCKOUT_MINUTES = 15
IP_LOCKOUT_MINUTES = 30
ATTEMPT_WINDOW_MINUTES = 15
_BANNED_IP_CACHE = {'expires_at': None, 'ips': set()}


def _banned_ip_cache_ttl_seconds() -> int:
    try:
        return max(0, int(os.environ.get('BOXCHAT_BANNED_IP_CACHE_TTL_SECONDS') or 30))
    except Exception:
        return 30


def _get_banned_ips_cached(now: datetime):
    ttl = _banned_ip_cache_ttl_seconds()
    expires_at = _BANNED_IP_CACHE.get('expires_at')
    if ttl > 0 and expires_at and expires_at > now:
        return _BANNED_IP_CACHE.get('ips') or set()

    ips = set()
    try:
        rows = (
            User.query.with_entities(User.banned_ips)
            .filter(User.is_banned.is_(True), User.banned_ips != '')
            .all()
        )
        for (raw,) in rows:
            if not raw:
                continue
            for token in str(raw).split(','):
                t = token.strip()
                if t:
                    ips.add(t)
    except Exception:
        ips = set()

    if ttl > 0:
        _BANNED_IP_CACHE['ips'] = ips
        _BANNED_IP_CACHE['expires_at'] = now + timedelta(seconds=ttl)
    return ips

def get_client_ip():
    return _get_client_ip(request) or ''

def validate_username(username):
    # Validate username format and length
    if not username or len(username) < 3:
        return False, "user name should be at least 3 characters long"
    
    if len(username) > 30:
        return False, "user name should be less than 30 characters long"
    
    # Only alphanumeric, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "user name can only contain letters, numbers, hyphens, and underscores"
    
    return True, ""

def validate_password(password):
    # Validate password strength
    if not password or len(password) < 8:
        return False, "password should be at least 8 characters long"
    
    if len(password) > 100:
        return False, "password should be less than 100 characters long"
    
    # Check for at least one uppercase, one lowercase, one digit
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '!@#$%^&*()-_=+[]{}|;:,.<>?' for c in password)
    
    if not (has_upper and has_lower and has_digit and has_special):
        return False, "password should contain uppercase, lowercase, digit and special symbol"
    
    return True, ""

def wants_json_response():
    if request.is_json:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept

def auth_error_response(message, status_code=400):
    if wants_json_response():
        return jsonify({'success': False, 'error': message}), status_code
    flash(message)
    return send_spa_index(), status_code

def get_request_value(name, default=''):
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return str(data.get(name, default) or default)
    return request.form.get(name, default)

def is_ip_banned(ip):
    # Check if IP is in banned list
    ip = str(ip or '').strip()
    if not ip:
        return False
    now = datetime.utcnow()
    return ip in _get_banned_ips_cached(now)

def is_true_value(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

def _cookie_max_age_seconds():
    lifetime = current_app.config.get('PERMANENT_SESSION_LIFETIME')
    if lifetime is None:
        return 30 * 24 * 60 * 60
    return int(lifetime.total_seconds())

def set_client_auth_cookies(response, user, remember_me):
    max_age = _cookie_max_age_seconds() if remember_me else None
    secure_flag = bool(current_app.config.get('SESSION_COOKIE_SECURE', False))
    same_site = current_app.config.get('SESSION_COOKIE_SAMESITE', 'Lax')
    response.set_cookie(
        'boxchat_uid',
        str(user.id),
        max_age=max_age,
        httponly=False,
        secure=secure_flag,
        samesite=same_site
    )
    response.set_cookie(
        'boxchat_uname',
        user.username,
        max_age=max_age,
        httponly=False,
        secure=secure_flag,
        samesite=same_site
    )
    response.set_cookie(
        'boxchat_auth_mode',
        'remember' if remember_me else 'session',
        max_age=max_age,
        httponly=False,
        secure=secure_flag,
        samesite=same_site
    )
    return response

def clear_client_auth_cookies(response):
    response.delete_cookie('boxchat_uid')
    response.delete_cookie('boxchat_uname')
    response.delete_cookie('boxchat_auth_mode')
    return response

def get_or_create_ip_throttle(ip):
    throttle = AuthThrottle.query.filter_by(ip_address=ip).first()
    if throttle:
        return throttle
    throttle = AuthThrottle(
        ip_address=ip,
        failed_attempts=0,
        lockout_until=None,
        last_attempt_at=None
    )
    db.session.add(throttle)
    db.session.flush()
    return throttle

def check_ip_lockout(ip, now):
    throttle = AuthThrottle.query.filter_by(ip_address=ip).first()
    if throttle and throttle.lockout_until and throttle.lockout_until > now:
        remaining_seconds = int((throttle.lockout_until - now).total_seconds())
        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
        return remaining_minutes
    return None

def register_ip_failed_attempt(ip, now):
    throttle = get_or_create_ip_throttle(ip)
    if throttle.last_attempt_at and (now - throttle.last_attempt_at) > timedelta(minutes=ATTEMPT_WINDOW_MINUTES):
        throttle.failed_attempts = 0
    throttle.failed_attempts = (throttle.failed_attempts or 0) + 1
    throttle.last_attempt_at = now
    if throttle.failed_attempts >= MAX_FAILED_IP_ATTEMPTS:
        throttle.lockout_until = now + timedelta(minutes=IP_LOCKOUT_MINUTES)
        throttle.failed_attempts = 0
    db.session.commit()

def reset_ip_throttle(ip, now):
    throttle = AuthThrottle.query.filter_by(ip_address=ip).first()
    if not throttle:
        return
    throttle.failed_attempts = 0
    throttle.lockout_until = None
    throttle.last_attempt_at = now
    db.session.commit()


def import_legacy_user_from_instance(username):
    # Fallback import for accounts that still exist in instance/thecomboxmsgr.db
    try:
        project_root = os.path.dirname(current_app.root_path)
        legacy_db_path = os.path.join(project_root, 'instance', 'thecomboxmsgr.db')
        if not os.path.exists(legacy_db_path):
            return None

        con = sqlite3.connect(legacy_db_path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        row = cur.execute(
            "SELECT username, password, bio, avatar_url, privacy_searchable, privacy_listable, "
            "hide_status, presence_status, is_superuser, is_banned, banned_ips, ban_reason "
            "FROM user WHERE lower(username)=lower(?) LIMIT 1",
            (username,)
        ).fetchone()
        con.close()
        if not row:
            return None

        exists = User.query.filter(func.lower(User.username) == str(row['username']).lower()).first()
        if exists:
            return exists

        user = User(
            username=row['username'],
            password=row['password'],
            bio=row['bio'] or '',
            avatar_url=row['avatar_url'],
            privacy_searchable=True if row['privacy_searchable'] is None else bool(row['privacy_searchable']),
            privacy_listable=True if row['privacy_listable'] is None else bool(row['privacy_listable']),
            hide_status=bool(row['hide_status']) if row['hide_status'] is not None else False,
            presence_status=row['presence_status'] or 'offline',
            is_superuser=bool(row['is_superuser']) if row['is_superuser'] is not None else False,
            is_banned=bool(row['is_banned']) if row['is_banned'] is not None else False,
            banned_ips=row['banned_ips'] or '',
            ban_reason=row['ban_reason']
        )
        db.session.add(user)
        db.session.commit()
        return user
    except Exception:
        db.session.rollback()
        return None

def _handle_login_post():
    username = get_request_value('username').strip()
    password = get_request_value('password')
    remember_me = is_true_value(get_request_value('remember_me'))
    client_ip = get_client_ip()
    now = datetime.utcnow()

    if not username or not password:
        return auth_error_response('username and password are required', 400)

    if is_ip_banned(client_ip):
        return auth_error_response('access denied', 403)

    ip_lock_minutes = check_ip_lockout(client_ip, now)
    if ip_lock_minutes:
        return auth_error_response(
            f'too many attempts from this IP, try again in {ip_lock_minutes} min',
            429
        )

    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if not user:
        user = import_legacy_user_from_instance(username)
    check_password_hash(DUMMY_PASSWORD_HASH, password)

    if user and user.lockout_until and user.lockout_until > now:
        remaining_seconds = int((user.lockout_until - now).total_seconds())
        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
        return auth_error_response(
            f'too many attempts, try again in {remaining_minutes} min',
            429
        )

    if user and user.is_banned:
        return auth_error_response('access denied', 403)

    if user and check_password_hash(user.password, password):
        user.failed_login_attempts = 0
        user.lockout_until = None
        user.last_login_at = now
        user.last_login_ip = client_ip
        db.session.commit()
        reset_ip_throttle(client_ip, now)

        session.clear()
        login_user(user, remember=remember_me)
        session.permanent = True
        session.modified = True

        if wants_json_response():
            response = jsonify({
                'success': True,
                'redirect': url_for('main.dashboard'),
                'user': {'id': user.id, 'username': user.username},
                'session': {
                    'remember': remember_me,
                    'cookie_name': current_app.config.get('SESSION_COOKIE_NAME', 'session')
                }
            })
            return set_client_auth_cookies(response, user, remember_me)

        response = redirect(url_for('main.dashboard'))
        return set_client_auth_cookies(response, user, remember_me)

    if user:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.lockout_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
        db.session.commit()
    register_ip_failed_attempt(client_ip, now)

    return auth_error_response('invalid username or password', 401)


def _handle_register_post():
    username = get_request_value('username').strip()
    password = get_request_value('password')
    confirm_password = get_request_value('confirm_password')
    remember_me = is_true_value(get_request_value('remember_me'))
    client_ip = get_client_ip()
    now = datetime.utcnow()

    if is_ip_banned(client_ip):
        return auth_error_response('access denied', 403)

    ip_lock_minutes = check_ip_lockout(client_ip, now)
    if ip_lock_minutes:
        return auth_error_response(
            f'too many attempts from this IP, try again in {ip_lock_minutes} min',
            429
        )

    is_valid, msg = validate_username(username)
    if not is_valid:
        return auth_error_response(msg, 400)

    is_valid, msg = validate_password(password)
    if not is_valid:
        return auth_error_response(msg, 400)

    if password != confirm_password:
        return auth_error_response('passwords do not match', 400)

    if User.query.filter(func.lower(User.username) == username.lower()).first():
        return auth_error_response('username already taken', 409)

    new_user = User(
        username=username,
        password=generate_password_hash(password, method='scrypt'),
        failed_login_attempts=0,
        lockout_until=None,
        last_login_ip=client_ip,
        last_login_at=now,
    )
    db.session.add(new_user)
    db.session.commit()
    reset_ip_throttle(client_ip, now)

    session.clear()
    login_user(new_user, remember=remember_me)
    session.permanent = True
    session.modified = True

    if wants_json_response():
        response = jsonify({
            'success': True,
            'redirect': url_for('main.dashboard'),
            'user': {'id': new_user.id, 'username': new_user.username},
            'session': {
                'remember': remember_me,
                'cookie_name': current_app.config.get('SESSION_COOKIE_NAME', 'session')
            }
        })
        response.status_code = 201
        return set_client_auth_cookies(response, new_user, remember_me)

    flash('account created successfully')
    response = redirect(url_for('main.dashboard'))
    return set_client_auth_cookies(response, new_user, remember_me)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # SPA route for login page + legacy form POST.
    if request.method == 'POST':
        return _handle_login_post()
    return send_spa_index()


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # SPA route for register page + legacy form POST.
    if request.method == 'POST':
        return _handle_register_post()
    return send_spa_index()


@auth_bp.route('/api/v1/auth/login', methods=['POST'])
def login_api():
    return _handle_login_post()


@auth_bp.route('/api/v1/auth/register', methods=['POST'])
def register_api():
    return _handle_register_post()

@auth_bp.route('/logout')
def logout():
    # Logout handler
    session.clear()
    logout_user()
    response = redirect(url_for('auth.login'))
    return clear_client_auth_cookies(response)

@auth_bp.route('/api/v1/auth/session', methods=['GET'])
def auth_session():
    if not current_user.is_authenticated:
        return jsonify({'authenticated': False}), 401
    return jsonify({
        'authenticated': True,
        'user': {
            'id': current_user.id,
            'username': current_user.username,
            'avatar_url': current_user.avatar_url or 'https://placehold.co/50x50',
            'is_superuser': bool(current_user.is_superuser),
        },
        'session': {
            'cookie_name': current_app.config.get('SESSION_COOKIE_NAME', 'session'),
            'remember_cookie_name': current_app.config.get('REMEMBER_COOKIE_NAME', 'remember_token'),
            'auth_mode': request.cookies.get('boxchat_auth_mode', 'session'),
            'uid_cookie': request.cookies.get('boxchat_uid')
        },
    })
