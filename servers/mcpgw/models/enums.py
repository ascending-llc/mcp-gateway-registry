from enum import Enum


class ToolDiscoveryMode(str, Enum):
    """Tool discovery mode enumeration"""
    EXTERNAL = "external"
    EMBEDDED = "embedded"


class DataSourceType(str, Enum):
    """Data source type + Weaviate Collection mapping"""
    S3 = ("s3", "S3Files")
    GOOGLE_DRIVE = ("gg", "GoogleDriveFiles")
    DATA_BASE = ("db", "DataBase")
    SHARE_POINT = ("sp", "SharePointFiles")

    def __new__(cls, value: str, collection: str):
        if not collection[0].isupper():
            raise ValueError(f"Collection name '{collection}' must start with an uppercase letter")
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.collection = collection
        return obj


class SearchType(str, Enum):
    """Search type enumeration"""
    NEAR_TEXT = "near_text"  # Semantic search
    NEAR_VECTOR = "near_vector"  # Vector search
    NEAR_IMAGE = "near_image"  # Image search
    BM25 = "bm25"  # Keyword search
    HYBRID = "hybrid"  # Hybrid search (semantic + keyword)
    FETCH_OBJECTS = "fetch_objects"  # Fetch objects
