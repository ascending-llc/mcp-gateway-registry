"""
Vector Storage Protocols

Defines interfaces that models must implement to be stored in vector databases.
"""

from typing import Protocol, runtime_checkable, ClassVar, Any, Set, List
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

            def to_documents(self) -> List[LangChainDocument]:
                return [LangChainDocument(page_content="...", metadata={...})]

            @classmethod
            def from_document(cls, document: LangChainDocument) -> dict:
                return {...}
    """

    # Required class variable
    COLLECTION_NAME: ClassVar[str]

    # Required instance variable
    id: Any

    @classmethod
    def from_document(cls, document: LangChainDocument) -> dict:
        """
        Create model instance data from LangChain Document.

        Args:
            document: LangChain Document from vector database

        Returns:
            Dictionary with model data (may not be complete model instance)
        """
        raise NotImplementedError()