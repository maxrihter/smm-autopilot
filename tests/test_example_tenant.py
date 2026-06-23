"""The bundled Barkwell example validates and `init` scaffolds it."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from smm_autopilot.cli import app
from smm_autopilot.config import Settings
from smm_autopilot.templates import example_tenant_yaml


def test_example_tenant_validates_as_settings() -> None:
    data = yaml.safe_load(example_tenant_yaml())
    s = Settings.model_validate(data)
    assert s.brand.name == "Barkwell"
    assert s.brand.content_language == "English"
    assert len(s.competitors) >= 3
    assert s.niche.keywords_l1
    assert s.region.events
    assert s.llm.analyst.primary.provider == "anthropic"


def test_init_scaffolds_and_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    first = runner.invoke(app, ["init"])
    assert first.exit_code == 0
    written = tmp_path / "config" / "tenant.yaml"
    assert written.exists()
    # what we wrote must itself load as valid Settings
    Settings.model_validate(yaml.safe_load(written.read_text()))

    second = runner.invoke(app, ["init"])
    assert second.exit_code == 0
    assert "already exists" in second.output  # did not overwrite
