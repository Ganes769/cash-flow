class XeroNotConnectedError(RuntimeError):
    """Raised when Xero API is called before OAuth login completes."""
