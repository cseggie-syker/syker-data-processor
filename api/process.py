"""Vercel serverless entrypoint for the FastAPI app."""

from backend.app import app

__all__ = ["app"]


