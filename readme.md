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

- Python 3.8 or higher

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
# BoxChat Messenger

BoxChat is a self-hosted messenger with a modern SPA frontend (Vite + React + MUI) and a Flask + Socket.IO backend.

Core features
- User accounts: register, login, session management
- Rooms & channels: multi-channel rooms, room settings, channel-level write permissions
- Direct messages (DMs) and friend requests
- Real-time messaging via Socket.IO with server-side validation
- Message actions: edit, delete, forward, reactions, reply
- Mentions and role-based mentions (including @everyone where allowed)
- Media: file uploads, image/GIF sending (Giphy integration), audio/video playback
- Presence, read receipts, notifications (per-user notification rooms)
- Moderation: mute, kick, ban (temporary), admin actions
- Roles & permissions per room, role management APIs

Documentation
- See the `docs/` folder for more detailed documentation: frontend, backend, API reference, sockets, setup and architecture.

Quick start (development)
```bash
# Python environment
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Frontend
cd frontend
npm install
npm run dev      # runs Vite dev server

# Back to repo root
cd ..
# Run DB migrations (project script)
python tools/migration.py

# Start server
python run.py
```

