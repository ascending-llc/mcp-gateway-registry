"""
Advanced Search Features

Provides support for advanced Weaviate features:
- Generative Search (RAG)
- Reranking
- Multi-vector search
- Image search
"""

import logging
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

from ..core.client import WeaviateClient
from ..core.enums import SearchType
from .query_builder import QueryBuilder

logger = logging.getLogger(__name__)


@dataclass
class GenerativeConfig:
    """Configuration for generative search (RAG)."""
    single_prompt: Optional[str] = None
    grouped_task: Optional[str] = None
    grouped_properties: Optional[List[str]] = None


@dataclass
class RerankConfig:
    """Configuration for search result reranking."""
    property: str
    query: Optional[str] = None


class GenerativeSearchMixin:
    """
    Mixin to add generative search capabilities to QueryBuilder.
    
    Generative search uses LLMs to generate summaries or answers
    based on search results (Retrieval-Augmented Generation).
    """
    
    def generative(
        self,
        single_prompt: Optional[str] = None,
        grouped_task: Optional[str] = None,
        grouped_properties: Optional[List[str]] = None
    ) -> 'QueryBuilder':
        """
        Enable generative search with custom prompts.
        
        Args:
            single_prompt: Prompt template for each result (e.g., "Summarize: {content}")
            grouped_task: Task to perform on all results together
            grouped_properties: Properties to include in grouped generation
            
        Returns:
            QueryBuilder instance
            
        Example:
            # Generate summary for each result
            results = (Article.objects
                .near_text("AI ethics")
                .generative(single_prompt="Summarize the key points: {content}")
                .all())
            
            # Generate combined analysis
            results = (Article.objects
                .hybrid("machine learning")
                .generative(grouped_task="Compare and contrast these articles")
                .all())
        """
        if not isinstance(self, QueryBuilder):
            raise TypeError("generative() can only be called on QueryBuilder")
        
        self.state.generative_config = {
            'single_prompt': single_prompt,
            'grouped_task': grouped_task,
            'grouped_properties': grouped_properties
        }
        
        return self
    
    def _execute_generative_search(self, collection, params: Dict[str, Any]):
        """
        Execute generative search using Weaviate's generate API.
        
        This is called internally by QueryExecutor when generative_config is set.
        """
        generative_config = params.pop('generative_config', None)
        if not generative_config:
            return None
        
        # Determine base search method
        search_type = params.get('search_type', SearchType.NEAR_TEXT)
        
        if search_type == SearchType.NEAR_TEXT:
            return collection.generate.near_text(
                query=params['query'],
                single_prompt=generative_config.get('single_prompt'),
                grouped_task=generative_config.get('grouped_task'),
                grouped_properties=generative_config.get('grouped_properties'),
                limit=params.get('limit'),
                filters=params.get('filters')
            )
        elif search_type == SearchType.HYBRID:
            return collection.generate.hybrid(
                query=params['query'],
                single_prompt=generative_config.get('single_prompt'),
                grouped_task=generative_config.get('grouped_task'),
                grouped_properties=generative_config.get('grouped_properties'),
                alpha=params.get('alpha', 0.7),
                limit=params.get('limit'),
                filters=params.get('filters')
            )
        elif search_type == SearchType.BM25:
            return collection.generate.bm25(
                query=params['query'],
                single_prompt=generative_config.get('single_prompt'),
                grouped_task=generative_config.get('grouped_task'),
                grouped_properties=generative_config.get('grouped_properties'),
                limit=params.get('limit'),
                filters=params.get('filters')
            )
        else:
            logger.warning(f"Generative search not supported for {search_type}")
            return None


class RerankMixin:
    """
    Mixin to add reranking capabilities to QueryBuilder.
    
    Reranking re-scores search results based on semantic similarity
    to a query, improving relevance.
    """
    
    def rerank(
        self,
        property: str,
        query: Optional[str] = None
    ) -> 'QueryBuilder':
        """
        Enable reranking of search results.
        
        Reranking uses a separate model to re-score results based on
        semantic similarity, potentially improving relevance.
        
        Args:
            property: Property to use for reranking
            query: Optional custom query for reranking (uses search query if None)
            
        Returns:
            QueryBuilder instance
            
        Example:
            # Rerank based on content similarity
            results = (Article.objects
                .near_text("machine learning")
                .rerank(property="content", query="deep learning algorithms")
                .all())
        """
        if not isinstance(self, QueryBuilder):
            raise TypeError("rerank() can only be called on QueryBuilder")
        
        self.state.rerank_config = {
            'property': property,
            'query': query
        }
        
        return self
    
    def _apply_rerank(self, query_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply reranking configuration to query parameters.
        
        This modifies the query params to include rerank configuration.
        """
        rerank_config = query_params.get('rerank_config')
        if not rerank_config:
            return query_params
        
        # Weaviate Python client rerank configuration
        # Note: Actual implementation depends on Weaviate client version
        from weaviate.classes.query import Rerank
        
        query_params['rerank'] = Rerank(
            prop=rerank_config['property'],
            query=rerank_config.get('query')
        )
        
        return query_params


class MultiVectorMixin:
    """
    Mixin to add multi-vector search capabilities.
    
    Multi-vector search allows searching with multiple vectors
    (e.g., text + image) and combining their results.
    """
    
    def multi_vector(
        self,
        vectors: Dict[str, List[float]],
        weights: Optional[Dict[str, float]] = None
    ) -> 'QueryBuilder':
        """
        Search with multiple vectors.
        
        Args:
            vectors: Dictionary mapping vector names to vector values
            weights: Optional weights for each vector (default: equal weights)
            
        Returns:
            QueryBuilder instance
            
        Example:
            results = (Article.objects
                .multi_vector({
                    'text': text_vector,
                    'image': image_vector
                }, weights={'text': 0.7, 'image': 0.3})
                .all())
        """
        if not isinstance(self, QueryBuilder):
            raise TypeError("multi_vector() can only be called on QueryBuilder")
        
        # Set search type and parameters for multi-vector
        self.state.search_type = SearchType.NEAR_VECTOR
        self.state.search_params['vectors'] = vectors
        self.state.search_params['weights'] = weights or {}
        
        return self


class ImageSearchMixin:
    """
    Mixin to add image search capabilities.
    
    Allows searching by image similarity.
    """
    
    def near_image(
        self,
        image: Union[str, bytes],
        **kwargs
    ) -> 'QueryBuilder':
        """
        Search for similar images.
        
        Args:
            image: Image data (base64 string or bytes)
            **kwargs: Additional search parameters
            
        Returns:
            QueryBuilder instance
            
        Example:
            # Search by image file
            with open('image.jpg', 'rb') as f:
                image_bytes = f.read()
            results = Article.objects.near_image(image_bytes).all()
            
            # Search by base64 string
            results = Article.objects.near_image(base64_image_string).all()
        """
        if not isinstance(self, QueryBuilder):
            raise TypeError("near_image() can only be called on QueryBuilder")
        
        self.state.search_type = SearchType.NEAR_IMAGE
        self.state.search_params = {'image': image, **kwargs}
        
        return self


# Extend QueryBuilder with advanced features
def extend_query_builder():
    """
    Extend QueryBuilder with advanced search features.
    
    This function is called during module initialization to add
    advanced methods to QueryBuilder.
    """
    from .query_builder import QueryBuilder
    
    # Add mixin methods to QueryBuilder
    for method_name in dir(GenerativeSearchMixin):
        if not method_name.startswith('_') and callable(getattr(GenerativeSearchMixin, method_name)):
            setattr(QueryBuilder, method_name, getattr(GenerativeSearchMixin, method_name))
    
    for method_name in dir(RerankMixin):
        if not method_name.startswith('_') and callable(getattr(RerankMixin, method_name)):
            setattr(QueryBuilder, method_name, getattr(RerankMixin, method_name))
    
    for method_name in dir(MultiVectorMixin):
        if not method_name.startswith('_') and callable(getattr(MultiVectorMixin, method_name)):
            setattr(QueryBuilder, method_name, getattr(MultiVectorMixin, method_name))
    
    for method_name in dir(ImageSearchMixin):
        if not method_name.startswith('_') and callable(getattr(ImageSearchMixin, method_name)):
            setattr(QueryBuilder, method_name, getattr(ImageSearchMixin, method_name))


# Auto-extend on import
extend_query_builder()

