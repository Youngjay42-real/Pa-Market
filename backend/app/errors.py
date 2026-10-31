"""Consistent API error envelope + global exception handling."""
from flask import jsonify
from werkzeug.exceptions import HTTPException
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError
from flask_limiter.errors import RateLimitExceeded


class ApiError(Exception):
    """Raise inside routes/services to fail a request with a stable payload."""

    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def as_json(self) -> dict:
        body = {"error": {"code": self.code, "message": self.message}}
        if self.details is not None:
            body["error"]["details"] = self.details
        body["message"] = self.message  # shallow mirror for simple frontend use
        return body


def body(code: str, message: str, status: int = 400, details=None):
    return jsonify(ApiError(status, code, message, details).as_json()), status


def register_error_handlers(app) -> None:
    """Uniform error responses; internal errors never leak stack traces."""

    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError):
        return jsonify(err.as_json()), err.status

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(err: RateLimitExceeded):
        return (
            jsonify(
                {
                    "error": {"code": "rate_limited", "message": "Too many requests."},
                    "message": "Too many requests. Please slow down.",
                }
            ),
            429,
        )

    @app.errorhandler(JWTExtendedException)
    def handle_jwt(err: JWTExtendedException):
        return (
            jsonify(
                {
                    "error": {"code": "unauthorized", "message": str(err)},
                    "message": "Authentication required.",
                }
            ),
            401,
        )

    @app.errorhandler(PyJWTError)
    def handle_pyjwt(err: PyJWTError):
        return (
            jsonify(
                {
                    "error": {"code": "unauthorized", "message": "Invalid token."},
                    "message": "Authentication required.",
                }
            ),
            401,
        )

    @app.errorhandler(HTTPException)
    def handle_http(err: HTTPException):
        code_map = {404: "not_found", 405: "method_not_allowed", 400: "bad_request"}
        return (
            jsonify(
                {
                    "error": {
                        "code": code_map.get(err.code, "http_error"),
                        "message": err.description or err.name,
                    },
                    "message": err.description or err.name,
                }
            ),
            err.code or 500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        if app.config.get("TESTING"):
            raise err  # let pytest see the real traceback
        app.logger.exception("Unhandled server error")
        return (
            jsonify(
                {
                    "error": {
                        "code": "internal_error",
                        "message": "Something went wrong. Please try again.",
                    },
                    "message": "Something went wrong. Please try again.",
                }
            ),
            500,
        )
