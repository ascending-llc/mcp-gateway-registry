"""Unit tests for auth_utils.scopes module."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from auth_utils.scopes import load_scopes_config, map_groups_to_scopes

SAMPLE_SCOPES_CONFIG = {
    "group_mappings": {
        "registry-admins": ["mcp-registry-admin", "mcp-servers-unrestricted/read"],
        "registry-users-lob1": ["registry-users-lob1"],
    }
}


@pytest.fixture
def sample_scopes_file(tmp_path: Path) -> Path:
    """Create a scopes.yml file with SAMPLE_SCOPES_CONFIG."""
    scopes_file = tmp_path / "scopes.yml"
    scopes_file.write_text(yaml.dump(SAMPLE_SCOPES_CONFIG))
    return scopes_file


class TestLoadScopesConfig:
    """Tests for load_scopes_config."""

    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        """Returns empty dict if scopes file does not exist."""
        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = tmp_path / "nonexistent.yml"
            result = load_scopes_config()
        assert result == {}

    def test_loads_valid_yaml(self, sample_scopes_file):
        """Returns parsed dict for a valid YAML scopes file."""
        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = sample_scopes_file
            result = load_scopes_config()

        assert result == SAMPLE_SCOPES_CONFIG

    def test_returns_empty_dict_for_non_dict_yaml(self, tmp_path):
        """Returns empty dict when YAML content is not a dict (e.g. a list)."""
        scopes_file = tmp_path / "scopes.yml"
        scopes_file.write_text("- item1\n- item2\n")

        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = scopes_file
            result = load_scopes_config()

        assert result == {}

    def test_returns_empty_dict_on_exception(self, tmp_path):
        """Returns empty dict when an unexpected error occurs."""
        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = tmp_path / "scopes.yml"
            # Patch open to raise
            with patch("builtins.open", side_effect=OSError("disk error")):
                result = load_scopes_config()
        assert result == {}


class TestMapGroupsToScopes:
    """Tests for map_groups_to_scopes."""

    def test_maps_known_group(self, sample_scopes_file):
        """Known groups are resolved to their configured scopes."""
        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = sample_scopes_file
            result = map_groups_to_scopes(["registry-admins"])

        assert result == ["mcp-registry-admin", "mcp-servers-unrestricted/read"]

    def test_unknown_group_returns_empty(self, sample_scopes_file):
        """Unknown groups produce no scopes."""
        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = sample_scopes_file
            result = map_groups_to_scopes(["unknown-group"])

        assert result == []

    def test_deduplicates_scopes(self, tmp_path):
        """Duplicate scopes from multiple groups are deduplicated while preserving order."""

        config = {
            "group_mappings": {
                "group-a": ["scope1", "scope2"],
                "group-b": ["scope2", "scope3"],
            }
        }
        scopes_file = tmp_path / "scopes.yml"
        scopes_file.write_text(yaml.dump(config))

        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = scopes_file
            result = map_groups_to_scopes(["group-a", "group-b"])

        assert result == ["scope1", "scope2", "scope3"]

    def test_empty_groups_list(self, sample_scopes_file):
        """Empty groups list returns empty scopes list."""
        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = sample_scopes_file
            result = map_groups_to_scopes([])

        assert result == []

    def test_missing_scopes_file_returns_empty(self, tmp_path):
        """Returns empty list when scopes file is missing."""
        with patch("auth_utils.scopes.settings") as mock_settings:
            mock_settings.scopes_config_path = tmp_path / "nonexistent.yml"
            result = map_groups_to_scopes(["registry-admins"])

        assert result == []
