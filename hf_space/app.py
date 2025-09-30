"""Entry point for the Hugging Face Space deployment.

This file simply re-exports the FastAPI application from the backend so the
Space runtime can discover and serve it.
"""

from backend.main import app
