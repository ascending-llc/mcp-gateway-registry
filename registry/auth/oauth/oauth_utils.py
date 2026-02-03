def parse_scope(scope: str | list[str] | None, default: list[str] = None) -> list[str]:
    """
    Parse OAuth scope field into a list of scopes.

    Args:
        scope: Can be a string (space or comma separated), a list of strings, or None
        default: Default value to return if scope is None

    Returns:
        List of scope strings
    """
    if scope is None:
        return default if default is not None else []

    if isinstance(scope, list):
        return scope

    if isinstance(scope, str):
        if "," in scope:
            return [s.strip() for s in scope.split(",") if s.strip()]
        return [s.strip() for s in scope.split() if s.strip()]

    return []


def scope_to_string(scope: str | list[str] | None) -> str:
    """
    Convert scope to a space-separated string.

    Args:
        scope: Can be a string, a list of strings, or None

    Returns:
        Space-separated string of scopes
    """
    if scope is None:
        return ""

    if isinstance(scope, list):
        return " ".join(scope)

    if isinstance(scope, str):
        return scope

    return ""
