from langchain_core.exceptions import LangChainException


class DependencyMissingError(LangChainException):
    """
    Required dependency package is missing.
    
    Provides clear installation instructions.
    """

    def __init__(self, package_name: str, message: str = None):
        if message is None:
            message = (
                f"Required package '{package_name}' is not installed.\n"
                f"Install with: pip install {package_name}\n"
                f"   or: uv add {package_name}"
            )
        super().__init__(message)
        self.package_name = package_name


class UnsupportedBackendError(LangChainException):
    """
    Unsupported database backend requested.
    
    Lists available backends for quick reference.
    """

    def __init__(self, backend_name: str, supported_backends: list = None):
        if supported_backends is None:
            from .enums import VectorStoreType
            supported_backends = [e.value for e in VectorStoreType]

        message = (
            f"Unsupported database backend: '{backend_name}'\n"
            f"Supported backends: {', '.join(supported_backends)}\n"
            f"Set VECTOR_STORE_TYPE or EMBEDDING_PROVIDER in .env file"
        )
        super().__init__(message)
        self.backend_name = backend_name
        self.supported_backends = supported_backends


class ConfigurationError(LangChainException):
    """
    Configuration error with helpful context.
    """

    def __init__(self, message: str, hint: str = None):
        full_message = f"Configuration error: {message}"
        if hint:
            full_message += f"\n{hint}"
        super().__init__(full_message)
        self.hint = hint
