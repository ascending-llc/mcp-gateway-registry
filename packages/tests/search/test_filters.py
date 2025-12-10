"""
Tests for the filter system (Q objects).
"""

import pytest
from weaviate.classes.query import Filter
from db.search.filters import (
    Q,
    and_,
    or_,
    not_
)


class TestQObject:
    """Test Q object functionality."""
    
    def test_simple_equality(self):
        """Test simple equality filter."""
        q = Q(category="tech")
        assert not q.is_empty()
        
        # Should convert to Weaviate filter
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_multiple_conditions(self):
        """Test multiple conditions in single Q object."""
        q = Q(category="tech", published=True)
        assert not q.is_empty()
        
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_gt(self):
        """Test greater than field lookup."""
        q = Q(views__gt=1000)
        assert not q.is_empty()
        
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_lt(self):
        """Test less than field lookup."""
        q = Q(views__lt=100)
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_gte(self):
        """Test greater than or equal field lookup."""
        q = Q(views__gte=1000)
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_lte(self):
        """Test less than or equal field lookup."""
        q = Q(views__lte=100)
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_ne(self):
        """Test not equal field lookup."""
        q = Q(status__ne="draft")
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_contains_any(self):
        """Test contains_any field lookup."""
        q = Q(tags__contains_any=["python", "java"])
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_contains_all(self):
        """Test contains_all field lookup."""
        q = Q(tags__contains_all=["python", "web"])
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_in(self):
        """Test in field lookup."""
        q = Q(category__in=["tech", "science"])
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_field_lookup_like(self):
        """Test like field lookup."""
        q = Q(title__like="*Python*")
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_invalid_operator(self):
        """Test invalid operator raises error."""
        with pytest.raises(ValueError, match="Unsupported operator"):
            Q(views__invalid_op=100)
    
    def test_or_operator(self):
        """Test OR operator between Q objects."""
        q1 = Q(category="tech")
        q2 = Q(category="science")
        combined = q1 | q2
        
        assert not combined.is_empty()
        assert combined._operator == "Or"
        
        weaviate_filter = combined.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_and_operator(self):
        """Test AND operator between Q objects."""
        q1 = Q(category="tech")
        q2 = Q(published=True)
        combined = q1 & q2
        
        assert not combined.is_empty()
        assert combined._operator == "And"
        
        weaviate_filter = combined.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_not_operator(self):
        """Test NOT operator (inversion)."""
        q = Q(category="obsolete")
        negated = ~q
        
        assert not negated.is_empty()
        assert negated._negated
        
        weaviate_filter = negated.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_complex_nested_conditions(self):
        """Test complex nested logical conditions."""
        q = (Q(category="tech") | Q(category="science")) & Q(views__gt=100)
        
        assert not q.is_empty()
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_triple_or(self):
        """Test three-way OR."""
        q = Q(category="tech") | Q(category="science") | Q(category="ai")
        
        assert not q.is_empty()
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_empty_q_object(self):
        """Test empty Q object."""
        q = Q()
        assert q.is_empty()
        assert q.to_weaviate_filter() is None
    
    def test_string_representation(self):
        """Test string representation."""
        q = Q(category="tech", views__gt=1000)
        q_str = str(q)
        assert "category" in q_str or "tech" in q_str
    
    def test_flattened_or_operations(self):
        """Test that OR operations are flattened."""
        q1 = Q(category="tech")
        q2 = Q(category="science")
        q3 = Q(category="ai")
        
        # Should flatten to single OR with three filters
        combined = q1 | q2 | q3
        
        assert combined._operator == "Or"
        # Check that filters are flattened (not nested)
        assert len(combined._filters) == 3
    
    def test_flattened_and_operations(self):
        """Test that AND operations are flattened."""
        q1 = Q(category="tech")
        q2 = Q(published=True)
        q3 = Q(views__gt=100)
        
        # Should flatten to single AND with three filters
        combined = q1 & q2 & q3
        
        assert combined._operator == "And"
        assert len(combined._filters) == 3


class TestConvenienceFunctions:
    """Test convenience functions for Q objects."""
    
    def test_and_function(self):
        """Test and_() convenience function."""
        q1 = Q(category="tech")
        q2 = Q(published=True)
        q3 = Q(views__gt=100)
        
        combined = and_(q1, q2, q3)
        
        assert not combined.is_empty()
        weaviate_filter = combined.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_or_function(self):
        """Test or_() convenience function."""
        q1 = Q(category="tech")
        q2 = Q(category="science")
        q3 = Q(category="ai")
        
        combined = or_(q1, q2, q3)
        
        assert not combined.is_empty()
        weaviate_filter = combined.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_not_function(self):
        """Test not_() convenience function."""
        q = Q(category="obsolete")
        negated = not_(q)
        
        assert not negated.is_empty()
        assert negated._negated
        
        weaviate_filter = negated.to_weaviate_filter()
        assert weaviate_filter is not None


# Note: FilterOperatorRegistry class has been removed as part of the simplification.
# Tests for Q object and convenience functions only.


class TestFilterIntegration:
    """Integration tests for filter system."""
    
    def test_real_world_query_pattern_1(self):
        """Test realistic query pattern - published tech articles with views."""
        q = Q(category="tech", published=True) & Q(views__gt=1000)
        
        assert not q.is_empty()
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_real_world_query_pattern_2(self):
        """Test realistic query pattern - multiple categories OR."""
        q = Q(category__in=["tech", "science", "ai"]) & Q(published=True)
        
        assert not q.is_empty()
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_real_world_query_pattern_3(self):
        """Test realistic query pattern - exclude drafts."""
        q = Q(published=True) & ~Q(status="draft") & Q(views__gt=100)
        
        assert not q.is_empty()
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_real_world_query_pattern_4(self):
        """Test realistic query pattern - tag filtering."""
        q = Q(tags__contains_any=["python", "javascript"]) & Q(category="tech")
        
        assert not q.is_empty()
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
    
    def test_complex_nested_logic(self):
        """Test deeply nested logical operations."""
        q = (
            (Q(category="tech") | Q(category="science")) &
            (Q(views__gt=1000) | Q(likes__gt=500)) &
            ~Q(status="draft")
        )
        
        assert not q.is_empty()
        weaviate_filter = q.to_weaviate_filter()
        assert weaviate_filter is not None
