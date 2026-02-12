# BoxChat Messenger

BoxChat is a simple, self-hosted messenger application.

## Stack

- **Backend:** Python, Flask, Socket.IO, JavaScript
- **Frontend:** HTML, CSS, JavaScript

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

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
npm install

# Start the server
python run.py
```

### Setup with Nix

```bash
# Activate nix shell
nix-shell

# Start the server
python run.py
```

