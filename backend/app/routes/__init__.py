"""Blueprint registry for the /api/v1 REST surface."""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .auth import auth_bp
    from .stands import stands_bp
    from .applications import applications_bp
    from .allocations import allocations_bp
    from .payments import payments_bp
    from .audit import audit_bp
    from .notifications import notifications_bp
    from .reports import reports_bp

    prefix = app.config["API_PREFIX"]
    app.register_blueprint(auth_bp, url_prefix=f"{prefix}/auth")
    app.register_blueprint(stands_bp, url_prefix=f"{prefix}/stands")
    app.register_blueprint(applications_bp, url_prefix=f"{prefix}/applications")
    app.register_blueprint(allocations_bp, url_prefix=f"{prefix}/allocations")
    app.register_blueprint(payments_bp, url_prefix=f"{prefix}/payments")
    app.register_blueprint(audit_bp, url_prefix=f"{prefix}/audit-logs")
    app.register_blueprint(notifications_bp, url_prefix=f"{prefix}/notifications")
    app.register_blueprint(reports_bp, url_prefix=f"{prefix}/reports")

    # Market Assistant (docs/CHATBOT_CONTRACT.md) — prefix follows API_PREFIX so
    # the endpoints stay under /api/v1/chatbot in every environment.
    from .chatbot import blueprint as chatbot_blueprint

    app.register_blueprint(chatbot_blueprint, url_prefix=f"{prefix}/chatbot")
