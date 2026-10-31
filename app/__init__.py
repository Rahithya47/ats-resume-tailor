"""Flask application factory."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask, render_template
from flask_wtf.csrf import CSRFError, CSRFProtect

from config import Config

csrf = CSRFProtect()


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    app.config["MAX_CONTENT_LENGTH"] = int(float(app.config["MAX_UPLOAD_MB"]) * 1024 * 1024)

    csrf.init_app(app)

    from app import context_store, database
    from app.resume_routes import bp as resume_bp
    from app.routes import bp

    database.init_app(app)
    context_store.init_app(app)
    app.register_blueprint(bp)
    app.register_blueprint(resume_bp)

    @app.template_filter("dt")
    def format_datetime(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M UTC")
        except (TypeError, ValueError):
            return "Unknown date"

    _register_error_handlers(app)
    return app


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(CSRFError)
    def csrf_failed(error):
        return (
            render_template(
                "500.html",
                title="Security check failed",
                message="Your form session expired or was invalid. Go back, reload the page and try again.",
            ),
            400,
        )

    @app.errorhandler(413)
    def too_large(_error):
        limit = app.config["MAX_UPLOAD_MB"]
        return (
            render_template(
                "analyze.html",
                form={},
                errors={"resume": f"The file is too large. The limit is {limit:g} MB."},
                max_mb=limit,
            ),
            413,
        )

    @app.errorhandler(500)
    def server_error(_error):
        return (
            render_template(
                "500.html",
                title="Something went wrong",
                message="An unexpected error occurred. Your data was not saved.",
            ),
            500,
        )
