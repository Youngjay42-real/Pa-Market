"""WSGI entrypoint for Gunicorn (Render) and the Flask CLI.

  development : flask --app wsgi.py run --debug       (or: FLASK_APP=wsgi.py)
  production  : gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 2
"""
import os
from pathlib import Path

from dotenv import load_dotenv  # type: ignore[import-untyped]

# Load ONLY backend/.env — the repo root's .env belongs to the Next.js/Prisma
# side and exporting its DATABASE_URL here would break the Flask config.
load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402

application = create_app(os.environ.get("FLASK_ENV", "development"))
# Flask CLI compatibility alias (FLASK_APP=wsgi.py expects `app` or `application`).
app = application

if __name__ == "__main__":
    application.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5001")), debug=True)
