"""Tenant Settings — defaults, engagement-floor lookup, YAML loading."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from smm_autopilot.config import EventConfig, Thresholds, default_settings, load_settings


def test_default_settings_valid() -> None:
    s = default_settings("Barkwell")
    assert s.brand.name == "Barkwell"
    assert s.llm.analyst.primary.provider  # llm defaulted in


def test_engagement_floor_lookup() -> None:
    s = default_settings()
    assert s.thresholds.engagement_floor("competitor") == (0, 0)
    assert s.thresholds.engagement_floor("unknown") == tuple(s.thresholds.default_engagement_floor)


def test_load_settings_from_yaml(tmp_path: Path) -> None:
    yaml_text = """
brand:
  name: Barkwell
  region: US
  content_language: English
competitors:
  - name: The Farmer's Dog
    instagram_url: https://instagram.com/thefarmersdog
niche:
  topic_whitelist: [product, education]
region:
  timezone: America/New_York
  events:
    - name: National Dog Day
      month: 8
      day: 26
thresholds:
  max_posts_after_filter: 100
"""
    path = tmp_path / "tenant.yaml"
    path.write_text(yaml_text)
    s = load_settings(path)
    assert s.brand.name == "Barkwell"
    assert s.competitors[0].name == "The Farmer's Dog"
    assert s.region.events[0].month == 8
    assert s.thresholds.max_posts_after_filter == 100


def test_bad_engagement_floor_rejected() -> None:
    # A one-element floor must fail at construction, not IndexError mid-pipeline.
    with pytest.raises(ValueError, match="engagement floor"):
        Thresholds(default_engagement_floor=[5000])


def test_event_next_occurrence_clamps_leap_day() -> None:
    ev = EventConfig(name="Leap", month=2, day=29)
    occ = ev.next_occurrence(date(2026, 1, 1))  # 2026 is not a leap year
    assert (occ.month, occ.day) == (2, 28)
