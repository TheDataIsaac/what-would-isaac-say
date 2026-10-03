"""Protects the API: the admin key check, the per-visitor rate limit and the daily cap."""

import secrets
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from isaac_says.api.deps import Resources, get_resources

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_admin(
    api_key: str | None = Depends(_api_key_header),
    resources: Resources = Depends(get_resources),
) -> None:
    """Allow the request only if it has the right admin key."""
    expected = resources.settings.admin_api_key
    if expected is None:
        # With no key set, the admin endpoints stay switched off.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Admin access is not configured.")
    # compare_digest takes the same time however many characters match, so timing cannot leak the key.
    if api_key is None or not secrets.compare_digest(api_key, expected.get_secret_value()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid API key.")


def client_address(request: Request, resources: Resources) -> str:
    """The visitor's address: from the proxy's header if we trust it, otherwise the direct caller."""
    if resources.settings.trust_client_ip_header:
        forwarded = request.headers.get("x-real-ip")
        if forwarded:
            return forwarded.strip()
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request, resources: Resources = Depends(get_resources)) -> None:
    client = client_address(request, resources)
    wait = resources.limiter.check(client)
    if wait > 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests. Please slow down.",
            headers={"Retry-After": str(int(wait) + 1)},
        )


async def daily_limit(resources: Resources = Depends(get_resources)) -> None:
    """Refuse chat messages once the day's total reaches the limit."""
    limit = resources.settings.daily_question_limit
    if limit == 0:
        return
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    if await resources.repo.count_queries_since(midnight) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "The assistant has reached its question limit for today. Please come back tomorrow.",
        )
