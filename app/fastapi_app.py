from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, Request


fastapi_app = FastAPI(title="BoxChat (async)", version="0.1.0")
_flask_app: Any | None = None


def init_fastapi(flask_app: Any) -> None:
    global _flask_app
    _flask_app = flask_app


def _require_flask_app() -> Any:
    if _flask_app is None:
        raise RuntimeError("FastAPI is not initialized (missing Flask app reference)")
    return _flask_app


def _decode_flask_session(request: Request) -> dict:
    flask_app = _require_flask_app()
    cookie_name = flask_app.config.get("SESSION_COOKIE_NAME", "session")
    raw = request.cookies.get(cookie_name)
    if not raw:
        return {}
    serializer = flask_app.session_interface.get_signing_serializer(flask_app)
    if serializer is None:
        return {}
    max_age = None
    try:
        lifetime = flask_app.permanent_session_lifetime
        if lifetime is not None:
            max_age = int(lifetime.total_seconds())
    except Exception:
        max_age = None
    try:
        data = serializer.loads(raw, max_age=max_age)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _get_session_user_id(request: Request) -> int | None:
    sess = _decode_flask_session(request)
    raw = sess.get("_user_id")
    try:
        return int(raw) if raw is not None else None
    except Exception:
        return None


async def _run_in_flask_context(fn, *args, **kwargs):
    flask_app = _require_flask_app()

    def _call():
        with flask_app.app_context():
            return fn(*args, **kwargs)

    return await asyncio.to_thread(_call)


@fastapi_app.get("/health")
async def health():
    return {"ok": True, "service": "boxchat", "framework": "fastapi"}


@fastapi_app.get("/v1/whoami")
async def whoami(request: Request):
    user_id = _get_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    def _load_user():
        from app.models import User

        user = User.query.get(int(user_id))
        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "avatar_url": user.avatar_url,
            "is_superuser": bool(getattr(user, "is_superuser", False)),
        }

    payload = await _run_in_flask_context(_load_user)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"authenticated": True, "user": payload}


@fastapi_app.get("/v1/statistics")
async def statistics(request: Request):
    user_id = _get_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    def _count_messages():
        from app.models import Message

        return int(Message.query.filter_by(user_id=int(user_id)).count())

    def _count_rooms():
        from app.models import Member

        return int(Member.query.filter_by(user_id=int(user_id)).count())

    msg_count, room_count = await asyncio.gather(
        _run_in_flask_context(_count_messages),
        _run_in_flask_context(_count_rooms),
    )
    return {"user_id": int(user_id), "total_messages": msg_count, "total_rooms": room_count}
