"""
Test configuration and fixtures for search framework tests.
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


@pytest.fixture
def mock_search_results():
    """Create mock search results."""
    mock_obj1 = MagicMock()
    mock_obj1.uuid = "uuid-1"
    mock_obj1.properties = {
        'title': 'Article 1',
        'content': 'Content about AI',
        'category': 'tech',
        'views': 100,
        'published': True
    }
    mock_obj1.metadata.distance = 0.1
    mock_obj1.metadata.score = 0.95
    
    mock_obj2 = MagicMock()
    mock_obj2.uuid = "uuid-2"
    mock_obj2.properties = {
        'title': 'Article 2',
        'content': 'Content about ML',
        'category': 'science',
        'views': 200,
        'published': True
    }
    mock_obj2.metadata.distance = 0.2
    mock_obj2.metadata.score = 0.85
    
    mock_response = MagicMock()
    mock_response.objects = [mock_obj1, mock_obj2]
    
    return mock_response


@pytest.fixture
def sample_articles_data():
    """Sample article data for testing."""
    return [
        {
            'id': 'uuid-1',
            'title': 'Machine Learning Basics',
            'content': 'Introduction to ML concepts',
            'category': 'tech',
            'views': 1500,
            'published': True,
            'tags': ['python', 'ml', 'ai']
        },
        {
            'id': 'uuid-2',
            'title': 'Deep Learning Advanced',
            'content': 'Advanced DL techniques',
            'category': 'tech',
            'views': 2000,
            'published': True,
            'tags': ['python', 'deep-learning', 'ai']
        },
        {
            'id': 'uuid-3',
            'title': 'Data Science Guide',
            'content': 'Guide to data science',
            'category': 'science',
            'views': 500,
            'published': False,
            'tags': ['python', 'data-science']
        }
    ]

