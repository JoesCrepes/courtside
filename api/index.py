"""Vercel entry point. Vercel serves the ASGI `app` found in this file."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(root), str(root / "src")]

from server.app import app  # noqa: E402

__all__ = ["app"]
