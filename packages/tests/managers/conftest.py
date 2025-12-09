"""
Test fixtures for managers tests.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add packages directory to path
packages_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(packages_dir))

from db.core.client import WeaviateClient
from db.models.model import Model
from db.models.base import TextField, IntField, BooleanField, TextArrayField


@pytest.fixture
def mock_weaviate_client():
    """Create a mock Weaviate client for testing."""
    client = Mock(spec=WeaviateClient)
    
    # Mock the managed_connection context manager
    mock_connection = MagicMock()
    mock_weaviate_instance = MagicMock()
    mock_connection.__enter__ = MagicMock(return_value=mock_weaviate_instance)
    mock_connection.__exit__ = MagicMock(return_value=None)
    client.managed_connection = MagicMock(return_value=mock_connection)
    
    # Mock collections
    mock_collection = MagicMock()
    mock_weaviate_instance.client.collections.get = MagicMock(return_value=mock_collection)
    mock_weaviate_instance.client.collections.exists = MagicMock(return_value=True)
    
    return client


@pytest.fixture
def test_model():
    """Create a test model class."""
    class TestArticle(Model):
        title = TextField(required=True)
        content = TextField(required=True)
        category = TextField(required=False)
        views = IntField(required=False)
        published = BooleanField(required=False)
        tags = TextArrayField(required=False)
        
        class Meta:
            collection_name = "TestArticles"
            vectorizer = "text2vec-openai"
    
    return TestArticle

