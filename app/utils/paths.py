from __future__ import annotations

from pathlib import Path


def safe_resolve_under(base_dir: str, user_path: str) -> Path | None:
    """Resolve user_path under base_dir and prevent path traversal."""
    try:
        base = Path(base_dir).resolve()
        rel = str(user_path or "").lstrip("/\\")
        target = (base / rel).resolve()
        if target == base or base in target.parents:
            return target
        return None
    except Exception:
        return None

