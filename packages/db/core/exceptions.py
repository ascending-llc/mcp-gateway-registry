"""
Custom exceptions for the ORM framework.
"""


class DoesNotExist(Exception):
    """Raised when an object matching the query does not exist"""
    pass


class MultipleObjectsReturned(Exception):
    """Raised when multiple objects are returned but only one was expected"""
    pass

