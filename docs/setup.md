**Setup & Run**

Prereqs
- Python 3.8+, node/npm (for frontend)
- Optional: Nix, if you use `shell.nix`

Dev (quick):
```bash
# create python venv
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# build or run frontend (two options)
cd frontend
npm install
npm run dev      # run vite for frontend dev
# or to build assets for production:
npm run build
cd ..

# run DB migrations (project has tools/migration.py)
python tools/migration.py

# start server
python run.py
```

Environment vars
- `FLASK_ENV` — optional
- `GIPHY_API_KEY` — optional to enable GIF search integration
- `UPLOAD_FOLDER` — directory for uploads (default: `uploads`)

Production notes
- Build frontend (`npm run build`) and serve via Flask static files or reverse proxy. The project contains SPA fallback routes and templates.

Troubleshooting
- If socket connections fail behind a proxy, ensure that websocket tunneling is enabled and `SESSION_COOKIE_SECURE` and CORS/socket origins are configured appropriately.
