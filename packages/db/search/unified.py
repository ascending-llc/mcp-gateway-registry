"""
Unified Search Interface

Provides a high-level, unified API for all search operations.
Combines model-based and collection-based searches into a single interface.
"""

import logging
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from ..core.client import WeaviateClient
from ..core.enums import SearchType
from .query_builder import QueryBuilder
from .targets import SearchTarget, create_target

logger = logging.getLogger(__name__)
T = TypeVar('T')


class UnifiedSearchInterface:
    """
    Unified search interface for both model-based and collection-based searches.
    
    This class provides a consistent API for searching Weaviate collections,
    whether you're working with defined models or raw collection names.
    
    Example:
        # Initialize
        search = UnifiedSearchInterface(client)
        
        # Model-based search
        results = search.model(Article).filter(category="tech").search("AI").all()
        
        # Collection-based search
        results = search.collection("Articles").filter(status="published").all()
        
        # Cross-collection search
        results = search.across(["Articles", "Documents"]).search("python").all()
        
        # Quick convenience methods
        results = search.bm25(Article, "machine learning")
        results = search.hybrid("Articles", "AI ethics", alpha=0.7)
    """
    
    def __init__(self, client: Optional[WeaviateClient] = None):
        """
        Initialize the unified search interface.
        
        Args:
            client: Weaviate client instance (will use global registry if None)
        """
        if client is None:
            from ..core.registry import get_weaviate_client
            client = get_weaviate_client()
        
        self.client = client
    
    # Primary Query Building Methods
    
    def model(self, model_class: Type[T]) -> QueryBuilder:
        """
        Create a query builder for a model class.
        
        Args:
            model_class: The model class to search
            
        Returns:
            QueryBuilder instance for chaining
            
        Example:
            search.model(Article).filter(category="tech").all()
        """
        return QueryBuilder(model_class, self.client)
    
    def collection(self, collection_name: str) -> QueryBuilder:
        """
        Create a query builder for a collection name.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            QueryBuilder instance for chaining
            
        Example:
            search.collection("Articles").filter(status="published").all()
        """
        return QueryBuilder(collection_name, self.client)
    
    def across(self, collection_names: List[str]) -> QueryBuilder:
        """
        Create a query builder for cross-collection search.
        
        Args:
            collection_names: List of collection names to search
            
        Returns:
            QueryBuilder instance configured for cross-collection search
            
        Example:
            search.across(["Articles", "Documents"]).search("python").all()
        """
        # Use first collection as base, then set all collections
        builder = QueryBuilder(collection_names[0], self.client)
        builder.across_collections(collection_names)
        return builder
    
    # Convenience Methods for Quick Searches
    
    def bm25(
        self,
        target: Union[Type[T], str],
        query: str,
        limit: int = 10,
        **kwargs
    ) -> List[Any]:
        """
        Quick BM25 keyword search.
        
        Args:
            target: Model class or collection name
            query: Search query
            limit: Maximum results
            **kwargs: Additional search parameters
            
        Returns:
            List of results
            
        Example:
            results = search.bm25(Article, "python programming", limit=5)
        """
        return (self._get_builder(target)
                .bm25(query, **kwargs)
                .limit(limit)
                .all())
    
    def near_text(
        self,
        target: Union[Type[T], str],
        text: str,
        limit: int = 10,
        **kwargs
    ) -> List[Any]:
        """
        Quick semantic search.
        
        Args:
            target: Model class or collection name
            text: Search text
            limit: Maximum results
            **kwargs: Additional search parameters
            
        Returns:
            List of results
            
        Example:
            results = search.near_text(Article, "artificial intelligence")
        """
        return (self._get_builder(target)
                .near_text(text, **kwargs)
                .limit(limit)
                .all())
    
    def hybrid(
        self,
        target: Union[Type[T], str],
        query: str,
        alpha: float = 0.7,
        limit: int = 10,
        **kwargs
    ) -> List[Any]:
        """
        Quick hybrid search.
        
        Args:
            target: Model class or collection name
            query: Search query
            alpha: Balance between semantic (1.0) and keyword (0.0)
            limit: Maximum results
            **kwargs: Additional search parameters
            
        Returns:
            List of results
            
        Example:
            results = search.hybrid(Article, "machine learning", alpha=0.8)
        """
        return (self._get_builder(target)
                .hybrid(query, alpha=alpha, **kwargs)
                .limit(limit)
                .all())
    
    def fuzzy(
        self,
        target: Union[Type[T], str],
        query: str,
        limit: int = 10,
        **kwargs
    ) -> List[Any]:
        """
        Quick fuzzy search (typo-tolerant).
        
        Args:
            target: Model class or collection name
            query: Search query (can have typos)
            limit: Maximum results
            **kwargs: Additional search parameters
            
        Returns:
            List of results
            
        Example:
            results = search.fuzzy(Article, "machin lernin")  # Finds "machine learning"
        """
        return (self._get_builder(target)
                .fuzzy(query, **kwargs)
                .limit(limit)
                .all())
    
    # Utility Methods
    
    def _get_builder(self, target: Union[Type[T], str]) -> QueryBuilder:
        """Get a query builder for the target."""
        if isinstance(target, str):
            return self.collection(target)
        else:
            return self.model(target)
    
    def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            True if collection exists
        """
        try:
            with self.client.managed_connection() as conn:
                return conn.client.collections.exists(collection_name)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False
    
    def collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Dictionary with collection info or None
        """
        try:
            with self.client.managed_connection() as conn:
                if not conn.client.collections.exists(collection_name):
                    return None
                
                collection = conn.client.collections.get(collection_name)
                config = collection.config.get()
                
                return {
                    'name': collection_name,
                    'properties': [prop.name for prop in config.properties],
                    'property_count': len(config.properties),
                }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return None
    
    def list_collections(self) -> List[str]:
        """
        List all available collections.
        
        Returns:
            List of collection names
        """
        try:
            with self.client.managed_connection() as conn:
                collections = conn.client.collections.list_all()
                return [c.name for c in collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []


# Global search interface instance
_global_search: Optional[UnifiedSearchInterface] = None


def get_search_interface(client: Optional[WeaviateClient] = None) -> UnifiedSearchInterface:
    """
    Get or create the global search interface instance.
    
    Args:
        client: Optional Weaviate client (required for first call)
        
    Returns:
        UnifiedSearchInterface instance
        
    Example:
        search = get_search_interface()
        results = search.model(Article).filter(category="tech").all()
    """
    global _global_search
    
    if _global_search is None:
        if client is None:
            from ..core.registry import get_weaviate_client
            client = get_weaviate_client()
        _global_search = UnifiedSearchInterface(client)
    
    return _global_search


def set_search_interface(search_interface: UnifiedSearchInterface) -> None:
    """
    Set the global search interface instance.
    
    Args:
        search_interface: Search interface instance to set as global
    """
    global _global_search
    _global_search = search_interface


# Convenience functions for quick access

def search_model(model_class: Type[T], client: Optional[WeaviateClient] = None) -> QueryBuilder:
    """
    Quick access to model-based search.
    
    Args:
        model_class: Model class to search
        client: Optional Weaviate client
        
    Returns:
        QueryBuilder instance
        
    Example:
        results = search_model(Article).filter(category="tech").all()
    """
    return get_search_interface(client).model(model_class)


def search_collection(collection_name: str, client: Optional[WeaviateClient] = None) -> QueryBuilder:
    """
    Quick access to collection-based search.
    
    Args:
        collection_name: Collection name
        client: Optional Weaviate client
        
    Returns:
        QueryBuilder instance
        
    Example:
        results = search_collection("Articles").filter(status="published").all()
    """
    return get_search_interface(client).collection(collection_name)
