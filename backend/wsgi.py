"""StandProof backend WSGI entry point.

Runs the chatbot service standalone (Developer 3). The backend lead will replace
this file with the full application wiring once the Flask foundation lands —
``create_app()`` only registers the chatbot blueprint for now.

Local run:
    cd backend
    python wsgi.py            # http://127.0.0.1:5000

Production (Render):
    gunicorn wsgi:app --bind 0.0.0.0:$PORT
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load backend/.env if present (python-dotenv when installed, tiny fallback otherwise)
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass

try:  # repo-root import layout:  backend.wsgi
    from backend.app import create_app
except ImportError:  # local run layout:  cd backend && python wsgi.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app import create_app

app = create_app()


if __name__ == "__main__":
    host = os.environ.get("CHATBOT_HOST", "0.0.0.0")
    port = int(os.environ.get("CHATBOT_PORT", "5000"))
    app.run(host=host, port=port, threaded=True)
