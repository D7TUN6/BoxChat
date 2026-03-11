from __future__ import annotations

import os
from typing import Any


def _is_true_env(name: str) -> bool:
    return str(os.environ.get(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def get_client_ip(request: Any) -> str | None:
    """Best-effort client IP with safe defaults.

    By default, does NOT trust proxy headers (X-Forwarded-For / X-Real-IP),
    because clients can spoof them. Enable explicitly when running behind a
    trusted reverse proxy: set BOXCHAT_TRUST_PROXY_HEADERS=1.
    """

    if _is_true_env("BOXCHAT_TRUST_PROXY_HEADERS"):
        try:
            xff = (request.headers.get("X-Forwarded-For") or "").strip()
            if xff:
                return xff.split(",")[0].strip() or None
        except Exception:
            pass
        try:
            xri = (request.headers.get("X-Real-IP") or "").strip()
            if xri:
                return xri
        except Exception:
            pass

    try:
        return getattr(request, "remote_addr", None)
    except Exception:
        return None

