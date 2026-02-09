"""
Utility functions for credential providers.
"""


def redact_sensitive_value(value: str, show_chars: int = 8) -> str:
    """
    Redact sensitive values like tokens, secrets, and passwords.

    Args:
        value: The sensitive value to redact
        show_chars: Number of characters to show before redacting (default: 8)

    Returns:
        Redacted string showing only first N characters followed by asterisks

    Example:
        >>> redact_sensitive_value("abc123xyz789", 8)
        "abc123xy********"
    """
    if not value or len(value) <= show_chars:
        return "*" * len(value) if value else ""

    return value[:show_chars] + "*" * (len(value) - show_chars)


def redact_credentials_in_text(text: str, show_chars: int = 8) -> str:
    """
    Redact common credential patterns in text output.

    Args:
        text: Text that may contain credentials
        show_chars: Number of characters to show before redacting

    Returns:
        Text with credentials redacted
    """
    import re

    # Patterns to redact (case insensitive)
    patterns = [
        r'(access_token["\s]*[:=]["\s]*)([^"\s]+)',
        r'(client_secret["\s]*[:=]["\s]*)([^"\s]+)',
        r'(secret["\s]*[:=]["\s]*)([^"\s]+)',
        r'(password["\s]*[:=]["\s]*)([^"\s]+)',
        r'(token["\s]*[:=]["\s]*)([^"\s]+)',
    ]

    result = text
    for pattern in patterns:

        def replace_match(match):
            prefix = match.group(1)
            value = match.group(2)
            redacted = redact_sensitive_value(value, show_chars)
            return f"{prefix}{redacted}"

        result = re.sub(pattern, replace_match, result, flags=re.IGNORECASE)

    return result
