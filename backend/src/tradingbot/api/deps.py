"""Typed dependency stubs for FastAPI's `Depends`.

create_app installs the real values via `app.dependency_overrides`, and tests
inject fakes the same way — so this module never imports adapters and the
stub bodies are never executed.
"""

from pathlib import Path

from tradingbot.application.persistence import Repositories


def get_repositories() -> Repositories:
    raise RuntimeError("Dependency not wired — create_app installs the override")


def get_walkforward_dir() -> Path:
    raise RuntimeError("Dependency not wired — create_app installs the override")


def get_paper_symbol() -> str:
    raise RuntimeError("Dependency not wired — create_app installs the override")
