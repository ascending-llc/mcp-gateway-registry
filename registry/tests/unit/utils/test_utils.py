"""
Unit tests for utility functions.
"""

import pytest

from registry.utils.utils import generate_server_name_from_title


@pytest.mark.unit
class TestGenerateServerNameFromTitle:
    """Test suite for generate_server_name_from_title function."""

    def test_special_characters_removed(self):
        """Test that special characters are removed."""
        assert generate_server_name_from_title("My-Server!@#$%^&*()") == "my-server"
        assert generate_server_name_from_title("Test Server!!!") == "test-server"
        assert generate_server_name_from_title("App (v2)") == "app-v2"
        assert generate_server_name_from_title("Server/Test") == "servertest"

    def test_multiple_spaces_collapsed(self):
        """Test that multiple spaces are collapsed to single hyphen."""
        assert generate_server_name_from_title("My   Server   Name") == "my-server-name"
        assert generate_server_name_from_title("Test    App") == "test-app"
        assert generate_server_name_from_title("Server      With      Spaces") == "server-with-spaces"

    def test_consecutive_hyphens_removed(self):
        """Test that consecutive hyphens are collapsed."""
        assert generate_server_name_from_title("My---Server") == "my-server"
        assert generate_server_name_from_title("Test--App") == "test-app"
        assert generate_server_name_from_title("Server-----------Name") == "server-name"

    def test_leading_trailing_hyphens_trimmed(self):
        """Test that leading and trailing hyphens are removed."""
        assert generate_server_name_from_title("-My Server-") == "my-server"
        assert generate_server_name_from_title("---Test App---") == "test-app"
        assert generate_server_name_from_title("-Server-") == "server"

    def test_empty_string_returns_fallback(self):
        """Test that empty string returns fallback value."""
        assert generate_server_name_from_title("") == "mcp-server"
        assert generate_server_name_from_title("   ") == "mcp-server"
        assert generate_server_name_from_title("\n\t") == "mcp-server"

    def test_only_special_chars_returns_fallback(self):
        """Test that string with only special characters returns fallback."""
        assert generate_server_name_from_title("!@#$%^&*()") == "mcp-server"
        assert generate_server_name_from_title("---") == "mcp-server"
        assert generate_server_name_from_title("!!!???") == "mcp-server"

    def test_preserves_existing_hyphens(self):
        """Test that existing hyphens in proper positions are preserved."""
        assert generate_server_name_from_title("pre-existing-hyphen") == "pre-existing-hyphen"
        assert generate_server_name_from_title("well-formed-slug") == "well-formed-slug"

    def test_mixed_case_converted_to_lowercase(self):
        """Test that mixed case is converted to lowercase."""
        assert generate_server_name_from_title("MyServer") == "myserver"
        assert generate_server_name_from_title("TestAPP") == "testapp"
        assert generate_server_name_from_title("CamelCaseTitle") == "camelcasetitle"

    def test_numbers_preserved(self):
        """Test that numbers are preserved in the slug."""
        assert generate_server_name_from_title("Server 123") == "server-123"
        assert generate_server_name_from_title("App v2.0") == "app-v20"
        assert generate_server_name_from_title("Test 2024") == "test-2024"

    def test_mixed_punctuation(self):
        """Test mixed punctuation scenarios."""
        assert generate_server_name_from_title("Server (Test): API v2.0!") == "server-test-api-v20"
        assert generate_server_name_from_title("My Server [Production]") == "my-server-production"
        assert generate_server_name_from_title("Test & Dev Server") == "test-dev-server"

    def test_length_preservation(self):
        """Test that reasonable length titles are handled correctly."""
        long_title = "Very Long Server Name With Many Words That Should Be Converted"
        expected = "very-long-server-name-with-many-words-that-should-be-converted"
        assert generate_server_name_from_title(long_title) == expected
