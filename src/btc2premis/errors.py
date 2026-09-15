"""Error types and process exit codes used by btc2premis."""

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_VALIDATION = 5
EXIT_FORBIDDEN = 6


class Btc2PremisError(Exception):
    """Base class for all expected (i.e. reported, not traced) errors."""

    exit_code = EXIT_ERROR


class UsageError(Btc2PremisError):
    """Invalid combination of command line arguments."""

    exit_code = EXIT_USAGE


class AuthenticationError(Btc2PremisError):
    """Login failed or the token was rejected."""

    exit_code = EXIT_AUTH


class AuthorizationError(Btc2PremisError):
    """Logged in successfully, but the account lacks permission for this request (HTTP 403)."""

    exit_code = EXIT_FORBIDDEN


class NotFoundError(Btc2PremisError):
    """The requested organization, crawl config or crawl does not exist."""

    exit_code = EXIT_NOT_FOUND


class ApiError(Btc2PremisError):
    """The Browsertrix API returned an unexpected response."""


class ValidationError(Btc2PremisError):
    """The generated PREMIS document failed schema validation."""

    exit_code = EXIT_VALIDATION
