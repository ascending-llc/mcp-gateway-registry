"""
Tests for BatchResult class.
"""

import pytest
from db.managers.batch import BatchResult


class TestBatchResult:
    """Test BatchResult class."""
    
    def test_initialization(self):
        """Test BatchResult initialization."""
        result = BatchResult(
            total=100,
            successful=95,
            failed=5,
            errors=[{'uuid': 'uuid-1', 'message': 'Error 1'}]
        )
        
        assert result.total == 100
        assert result.successful == 95
        assert result.failed == 5
        assert len(result.errors) == 1
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        result = BatchResult(total=100, successful=95, failed=5, errors=[])
        
        assert result.success_rate == 95.0
    
    def test_success_rate_edge_cases(self):
        """Test success rate with edge cases."""
        # Zero total
        result = BatchResult(total=0, successful=0, failed=0, errors=[])
        assert result.success_rate == 0.0
        
        # All successful
        result = BatchResult(total=100, successful=100, failed=0, errors=[])
        assert result.success_rate == 100.0
        
        # All failed
        result = BatchResult(total=100, successful=0, failed=100, errors=[])
        assert result.success_rate == 0.0
    
    def test_is_complete_success(self):
        """Test is_complete_success property."""
        # Complete success
        result = BatchResult(total=100, successful=100, failed=0, errors=[])
        assert result.is_complete_success is True
        
        # Partial success
        result = BatchResult(total=100, successful=95, failed=5, errors=[])
        assert result.is_complete_success is False
        
        # Complete failure
        result = BatchResult(total=100, successful=0, failed=100, errors=[])
        assert result.is_complete_success is False
    
    def test_has_errors(self):
        """Test has_errors property."""
        # No errors
        result = BatchResult(total=100, successful=100, failed=0, errors=[])
        assert result.has_errors is False
        
        # With errors
        result = BatchResult(total=100, successful=95, failed=5, errors=[{'uuid': 'x'}])
        assert result.has_errors is True
    
    def test_string_representation(self):
        """Test string representation."""
        result = BatchResult(total=100, successful=95, failed=5, errors=[])
        
        result_str = str(result)
        
        assert "100" in result_str
        assert "95" in result_str
        assert "5" in result_str
        assert "95.0%" in result_str
    
    def test_boolean_conversion(self):
        """Test boolean conversion."""
        # Has successful operations - truthy
        result = BatchResult(total=100, successful=95, failed=5, errors=[])
        assert bool(result) is True
        
        # All failed - falsy
        result = BatchResult(total=100, successful=0, failed=100, errors=[])
        assert bool(result) is False
        
        # Zero operations - falsy
        result = BatchResult(total=0, successful=0, failed=0, errors=[])
        assert bool(result) is False

