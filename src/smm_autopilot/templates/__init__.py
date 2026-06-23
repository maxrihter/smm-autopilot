"""Bundled starter templates (shipped in the wheel).

The example tenant config is the single source of truth for what a real
configuration looks like; ``smm-autopilot init`` scaffolds from it.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@cache
def example_tenant_yaml() -> str:
    """Return the bundled example tenant config (the fictional Barkwell brand)."""
    return (_DIR / "tenant.example.yaml").read_text(encoding="utf-8")
