class XeroNotConnectedError(RuntimeError):
    """Raised when Xero API is called before OAuth login completes."""


class XeroRateLimitError(RuntimeError):
    """Raised when Xero refuses calls until a rate-limit window resets."""

    def __init__(self, retry_after: int, problem: str | None = None):
        self.retry_after = max(1, int(retry_after))
        self.problem = (problem or "day").strip().lower()
        super().__init__(_rate_limit_message(self.retry_after, self.problem))


def _rate_limit_message(retry_after: int, problem: str) -> str:
    if retry_after >= 3600:
        wait = f"about {max(1, round(retry_after / 3600))} hours"
    elif retry_after >= 60:
        wait = f"about {max(1, round(retry_after / 60))} minutes"
    else:
        wait = f"{retry_after} seconds"
    limit = "daily" if problem == "day" else "per-minute"
    return f"Xero {limit} API limit is used up. Sync is paused for {wait}."


def rate_limit_error(exc) -> XeroRateLimitError | None:
    if getattr(exc, "status", None) != 429:
        return None
    headers = getattr(exc, "headers", None) or {}
    getter = headers.get if hasattr(headers, "get") else lambda _key, default=None: default
    raw_after = getter("Retry-After")
    try:
        retry_after = int(float(raw_after))
    except (TypeError, ValueError):
        retry_after = 3600
    problem = getter("X-Rate-Limit-Problem") or "day"
    return XeroRateLimitError(retry_after, str(problem))
