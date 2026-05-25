class TheKeysApiError(Exception):
    """Base exception for TheKeysApi errors."""
    pass


class NoAccessoriesFoundError(TheKeysApiError):
    """Raised when no accessories are found for a lock."""
    pass


class NoGatewayAccessoryFoundError(TheKeysApiError):
    """Raised when no gateway accessory is found for a lock."""
    pass


class GatewayAccessoryNotFoundError(TheKeysApiError):
    """Raised when the gateway accessory could not be retrieved from the API."""
    pass


class NoGatewayIpFoundError(TheKeysApiError):
    """Raised when no gateway IP is found for a lock."""
    pass


class NoSharesFoundError(TheKeysApiError):
    """Raised when no shares are found for a lock."""
    pass


class NoUtilisateurFoundError(TheKeysApiError):
    """Raised when the user could not be retrieved from the API."""
    pass


class GatewayUnreachableError(TheKeysApiError, ConnectionError):
    """Raised when the gateway cannot be reached (timeout or connection error).

    Wraps requests.Timeout / requests.ConnectionError so callers see a library
    exception instead of leaking requests internals. Also subclasses ConnectionError
    so existing ``except ConnectionError`` handlers keep catching it (backward
    compatible).
    """

    def __init__(self, host: str, original: Exception) -> None:
        super().__init__(f"Gateway {host} unreachable: {original}")
        self.host = host
        self.original = original
