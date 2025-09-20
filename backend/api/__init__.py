"""API package exposing routers and dependency configuration."""

from .routes import configure_services, router

__all__ = ["router", "configure_services"]
