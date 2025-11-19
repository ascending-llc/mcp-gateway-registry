"""
MCPGW Vector Search Module

This module provides vector search functionality for the MCPGW server,
supporting both embedded FAISS and external vector search services.
"""

from .service import vector_search_service

__all__ = ['vector_search_service']
