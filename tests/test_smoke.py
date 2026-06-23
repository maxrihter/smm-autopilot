"""Smoke tests — the package imports and the CLI wires up."""

from __future__ import annotations

import smm_autopilot
from smm_autopilot.cli import app


def test_version_is_set() -> None:
    assert smm_autopilot.__version__


def test_cli_app_exists() -> None:
    assert app is not None
