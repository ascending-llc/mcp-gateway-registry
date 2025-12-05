"""
Batch operation result tracking.

Provides comprehensive feedback for batch operations following
Weaviate's best practices for error handling.

Reference: https://docs.weaviate.io/weaviate/manage-objects/import
"""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class BatchResult:
    """
    Result of a batch operation with success/failure tracking.
    
    Provides complete statistics about batch operations including
    success/failure counts and detailed error information.
    
    Attributes:
        total: Total number of operations attempted
        successful: Number of successful operations
        failed: Number of failed operations
        errors: List of error dictionaries with 'uuid' and 'message'
    
    Example:
        result = Article.objects.bulk_create(articles)
        print(f"Success: {result.successful}/{result.total}")
        print(f"Success rate: {result.success_rate}%")
        
        if result.failed > 0:
            print(f"Errors: {result.errors[:5]}")  # Show first 5 errors
    """
    total: int
    successful: int
    failed: int
    errors: List[Dict[str, Any]]
    
    @property
    def success_rate(self) -> float:
        """
        Calculate success rate as percentage.
        
        Returns:
            Success rate from 0.0 to 100.0
        """
        return (self.successful / self.total * 100) if self.total > 0 else 0.0
    
    @property
    def is_complete_success(self) -> bool:
        """
        Check if all operations succeeded.
        
        Returns:
            True if no failures, False otherwise
        """
        return self.failed == 0
    
    @property
    def has_errors(self) -> bool:
        """
        Check if any operations failed.
        
        Returns:
            True if there are failures
        """
        return self.failed > 0
    
    def __str__(self) -> str:
        """String representation for easy logging."""
        return (
            f"BatchResult(total={self.total}, "
            f"successful={self.successful}, "
            f"failed={self.failed}, "
            f"success_rate={self.success_rate:.1f}%)"
        )
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def __bool__(self) -> bool:
        """
        Boolean conversion.
        
        Treats result as True if any operations succeeded.
        """
        return self.successful > 0

