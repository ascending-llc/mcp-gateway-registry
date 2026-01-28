"""
Vector Storage Protocols

Defines interfaces that models must implement to be stored in vector databases.
"""

from typing import Protocol, runtime_checkable, ClassVar, Any, Set
from langchain_core.documents import Document as LangChainDocument


@runtime_checkable
class VectorStorable(Protocol):
    """
    Protocol for models that can be stored in vector databases.

    Any model implementing this protocol can be used with Repository.
    The @runtime_checkable decorator enables isinstance() checks.

    Example:
        class MyModel:
            COLLECTION_NAME = "my_collection"
            id: str

            def to_document(self) -> LangChainDocument:
                return LangChainDocument(page_content="...", metadata={...})

            @classmethod
            def from_document(cls, document: LangChainDocument) -> dict:
                return {...}
    """

    # Required class variable
    COLLECTION_NAME: ClassVar[str]

    # Required instance variable
    id: Any

    def to_document(self) -> LangChainDocument:
        """
        Convert model instance to LangChain Document for vector storage.

        Returns:
            LangChain Document with page_content and metadata
        """
        ...

    @classmethod
    def from_document(cls, document: LangChainDocument) -> dict:
        """
        Create model instance data from LangChain Document.

        Args:
            document: LangChain Document from vector database

        Returns:
            Dictionary with model data (may not be complete model instance)
        """
        ...

    @staticmethod
    def get_safe_metadata_fields() -> Set[str]:
        """
        Get fields that can be updated without re-vectorization.

        Returns:
            Set of safe metadata field names
        """
        ...


@runtime_checkable
class ContentGenerator(Protocol):
    """
    Protocol for models that can generate searchable content.

    This is used for smart update detection.
    """

    def generate_content(self) -> str:
        """
        Generate searchable text content for vectorization.

        Returns:
            Combined text string for semantic search
        """
        ...