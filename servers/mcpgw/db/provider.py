import logging
import threading

from db.client import WeaviateClient
from db.search import WeaviateSearchService

logger = logging.getLogger(__name__)


class WeaviateSearchSingleton:
    """
    Thread-safe WeaviateService singleton class

    Provides a single global instance of WeaviateService to avoid
    multiple initialization of the same services.
    """
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """
        Get singleton instance of WeaviateService

        Returns:
            WeaviateService: Singleton service instance
        """
        if cls._instance is None:
            with cls._lock:  # Thread-safe
                if cls._instance is None:  # Double-check
                    logger.info("Initializing global WeaviateService (singleton)")

                    cls._instance = WeaviateSearchService(client=WeaviateClient())
        return cls._instance


def get_weaviate_search():
    return WeaviateSearchSingleton.get_instance()
