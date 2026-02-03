"""
Batch result utilities for bulk operations.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class BatchResult:
    """
    Result of a batch operation containing success/failure statistics and error details.

    Attributes:
        total: Total number of items processed
        successful: Number of successfully processed items
        failed: Number of failed items
        errors: List of error details with UUIDs and messages
    """

    total: int
    successful: int
    failed: int
    errors: list[dict[str, Any]]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100.0

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def __str__(self) -> str:
        return f"BatchResult(total={self.total}, successful={self.successful}, failed={self.failed}, errors={len(self.errors)})"

    def __repr__(self) -> str:
        return self.__str__()
