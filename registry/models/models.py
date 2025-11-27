from enum import Enum


class SearchType(str, Enum):
    """Search type enumeration"""
    NEAR_TEXT = "near_text"  # Semantic search
    NEAR_VECTOR = "near_vector"  # Vector search
    NEAR_IMAGE = "near_image"  # Image search
    BM25 = "bm25"  # Keyword search
    HYBRID = "hybrid"  # Hybrid search (semantic + keyword)
    FETCH_OBJECTS = "fetch_objects"  # Fetch objects