"""
Base federation client interface.

Provides common functionality for all federation clients.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


class BaseFederationClient(ABC):
    """Base class for federation clients."""

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: int = 30,
        retry_attempts: int = 3
    ):
        """
        Initialize federation client.

        Args:
            endpoint: Base URL for the federation API
            timeout_seconds: HTTP request timeout
            retry_attempts: Number of retry attempts for failed requests
        """
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.client = httpx.Client(timeout=timeout_seconds)

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "client"):
            self.client.close()

    @abstractmethod
    def fetch_server(
        self,
        server_name: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single server from the federated registry.

        Args:
            server_name: Name of the server to fetch
            **kwargs: Additional parameters specific to the federation source

        Returns:
            Server data dictionary or None if fetch fails
        """
        pass

    @abstractmethod
    def fetch_all_servers(
        self,
        server_names: List[str],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch multiple servers from the federated registry.

        Args:
            server_names: List of server names to fetch
            **kwargs: Additional parameters specific to the federation source

        Returns:
            List of server data dictionaries
        """
        pass

    def _make_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with retry logic.

        Args:
            url: Full URL to request
            method: HTTP method (GET, POST, etc.)
            headers: HTTP headers
            params: Query parameters
            data: Request body data

        Returns:
            Response JSON or None if request fails
        """
        for attempt in range(self.retry_attempts):
            try:
                logger.debug(f"Making {method} request to {url} (attempt {attempt + 1}/{self.retry_attempts})")

                response = self.client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=data
                )

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} for {url}: {e}")
                if e.response.status_code in [404, 401, 403]:
                    # Don't retry for these errors
                    return None
                if attempt == self.retry_attempts - 1:
                    return None

            except httpx.RequestError as e:
                logger.error(f"Request error for {url}: {e}")
                if attempt == self.retry_attempts - 1:
                    return None

            except Exception as e:
                logger.error(f"Unexpected error for {url}: {e}")
                if attempt == self.retry_attempts - 1:
                    return None

        return None
