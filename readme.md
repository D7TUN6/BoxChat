# BoxChat Messenger

BoxChat is a simple, self-hosted messenger application.

## Stack

- **Backend:** Python, Flask, Socket.IO, JavaScript
- **Frontend:** Vite, React, MaterialUI

## Credits

- **D7TUN6:** Founder, leader, full stack developer
- **Nekto:** Tester, frontend fixer
- **Toffo:** Future redesign and UI/UX designer
- **Sophron:** Added some new reactions
- **Ernela:** Frontend rewrite, much small new functions and fixes

## Status

This project is maintained on a best-effort basis. Contributions are welcome!

## Important
v3.0 is the last python version! in the next version backend will be rewritten from python to go

## Getting Started

### Requirements

- Python 3.10 or higher

## Environment variables

- `BOXCHAT_SECRET_KEY`: overrides `SECRET_KEY` (don’t keep a default/weak key in `config.json`).
- `BOXCHAT_ADMIN_PASSWORD`: creates a bootstrap `admin` user on first run (only if `admin` does not exist).
- `BOXCHAT_SOCKETIO_CORS_ALLOWED_ORIGINS`: Socket.IO CORS (default is same-origin). Use `*` or a comma-separated list for dev.
- `BOXCHAT_MAX_CONTENT_LENGTH`: max upload size in bytes (default: `5368709120` = 5 GiB).
- `BOXCHAT_TRUST_PROXY_HEADERS`: if `1`, trusts `X-Forwarded-For`/`X-Real-IP` for IP-based bans/lockouts (only enable behind a trusted proxy).
- `BOXCHAT_BANNED_IP_CACHE_TTL_SECONDS`: cache TTL for banned IP set (default: `30`).

## FastAPI (async)

FastAPI is mounted under `GET /api/async` when `fastapi` + `a2wsgi` are installed.

- Docs: `GET /api/async/docs`
- Health: `GET /api/async/health`
- Session user: `GET /api/async/v1/whoami`
- Stats (parallelized counts): `GET /api/async/v1/statistics`

### Setup with venv

```bash
python -m venv boxchat-venv

# Activate virtual environment
# On Windows:
boxchat-venv\Scripts\activate

# On Linux/macOS:
source boxchat-venv/bin/activate

# Install dependencies and build frontend
pip install --upgrade pip
pip install -r requirements.txt
cd frontend && npm install && npm run build

# Run migrations
cd ..
python tools/migration.py

# Start the server
python run.py
```

### Setup with Nix

```bash
# Activate nix shell
nix-shell
python tools/migration.py

# Start the server
python run.py
```
