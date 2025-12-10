"""
Tests for exception hierarchy.
"""

import pytest
from db.core.exceptions import *


class TestExceptionHierarchy:
    """Test exception class hierarchy."""
    
    def test_base_exception(self):
        """Test WeaviateORMException as base."""
        exc = WeaviateORMException("test")
        
        assert isinstance(exc, Exception)
        assert "test" in str(exc)
    
    def test_connection_exception_hierarchy(self):
        """Test connection exception hierarchy."""
        exc = ConnectionException("localhost", 8099, "Connection timeout")
        
        assert isinstance(exc, ConnectionException)
        assert isinstance(exc, WeaviateORMException)
        assert "localhost:8099" in str(exc)
        assert "Connection timeout" in str(exc)
    
    def test_configuration_exception_hierarchy(self):
        """Test configuration exception hierarchy."""
        exc = ConfigurationException("Invalid configuration")
        
        assert isinstance(exc, ConfigurationException)
        assert isinstance(exc, WeaviateORMException)
        assert "Invalid configuration" in str(exc)
    
    def test_query_exception_hierarchy(self):
        """Test query exception hierarchy."""
        exc = DoesNotExist("Article", {"title": "Test"})
        
        assert isinstance(exc, QueryException)
        assert isinstance(exc, WeaviateORMException)


class TestDoesNotExist:
    """Test DoesNotExist exception."""
    
    def test_with_filters(self):
        """Test DoesNotExist with filter information."""
        exc = DoesNotExist("Article", {"title": "Test", "category": "tech"})
        
        assert exc.model_name == "Article"
        assert exc.filters == {"title": "Test", "category": "tech"}
        assert "Article" in str(exc)
        assert "title" in str(exc)
    
    def test_without_filters(self):
        """Test DoesNotExist without filters."""
        exc = DoesNotExist("Article")
        
        assert exc.model_name == "Article"
        assert exc.filters == {}
        assert "Article" in str(exc)


class TestMultipleObjectsReturned:
    """Test MultipleObjectsReturned exception."""
    
    def test_with_count(self):
        """Test exception with object count."""
        exc = MultipleObjectsReturned("Article", 5)
        
        assert exc.model_name == "Article"
        assert exc.count == 5
        assert "Expected 1" in str(exc)
        assert "got 5" in str(exc)
    
    def test_with_filters(self):
        """Test exception with filters."""
        exc = MultipleObjectsReturned("Article", 3, {"category": "tech"})
        
        assert exc.filters == {"category": "tech"}
        assert "Article" in str(exc)


class TestFieldValidationError:
    """Test FieldValidationError exception."""
    
    def test_with_context(self):
        """Test exception with full context."""
        exc = FieldValidationError("title", "x", "Too short")
        
        assert exc.field_name == "title"
        assert exc.value == "x"
        assert exc.reason == "Too short"
        assert "title" in str(exc)
        assert "Too short" in str(exc)


class TestCollectionExceptions:
    """Test collection-related exceptions."""
    
    def test_collection_not_found(self):
        """Test CollectionNotFound exception."""
        exc = CollectionNotFound("Articles")
        
        assert exc.collection_name == "Articles"
        assert "Articles" in str(exc)
        assert "not found" in str(exc)


class TestDataOperationException:
    """Test data operation exceptions."""
    
    def test_insert_failed(self):
        """Test InsertFailed exception."""
        exc = InsertFailed("Articles", "Connection timeout")
        
        assert exc.collection_name == "Articles"
        assert exc.reason == "Connection timeout"
        assert "Articles" in str(exc)
        assert "Connection timeout" in str(exc)
