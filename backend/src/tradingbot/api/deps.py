"""Typed dependency stubs for FastAPI's `Depends`.

create_app installs the real values via `app.dependency_overrides`, and tests
inject fakes the same way — so this module never imports adapters and the
stub bodies are never executed.
"""

from tradingbot.application.persistence import Repositories


def get_repositories() -> Repositories:
    raise RuntimeError("Dependency not wired — create_app installs the override")
