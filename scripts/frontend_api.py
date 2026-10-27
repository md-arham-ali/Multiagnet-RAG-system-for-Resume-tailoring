"""
Shim. The bridge API lives in backend/ now.

Kept because the run command, nginx.conf and vite.config.js all hardcode
scripts.frontend_api:app, so deleting this means editing all three.

    .venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import app  # noqa: E402,F401
