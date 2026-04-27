"""Tests for config/data_sources.yaml SSoT (KIK-736).

Verifies the YAML structure is parsable and contains the expected domains.
This is a contract test: changes to data_sources.yaml require updating this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


_DATA_SOURCES_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "data_sources.yaml"
)


@pytest.fixture(scope="module")
def data_sources():
    with open(_DATA_SOURCES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestDataSourcesYaml:
    def test_file_exists(self):
        assert _DATA_SOURCES_PATH.exists()

    def test_has_domains_root(self, data_sources):
        assert "domains" in data_sources
        assert isinstance(data_sources["domains"], dict)

    def test_pf_domain_required_includes_cash(self, data_sources):
        pf = data_sources["domains"]["pf"]
        required_paths = [
            r["path"] for r in pf["required"] if "path" in r
        ]
        assert "data/portfolio.csv" in required_paths
        assert "data/cash_balance.json" in required_paths

    def test_each_domain_has_required(self, data_sources):
        for name, cfg in data_sources["domains"].items():
            assert "required" in cfg, f"domain '{name}' missing 'required'"
            assert isinstance(cfg["required"], list)

    def test_domains_present(self, data_sources):
        # Required minimal set
        for d in ("pf", "market", "sector", "stock"):
            assert d in data_sources["domains"], f"missing domain: {d}"
