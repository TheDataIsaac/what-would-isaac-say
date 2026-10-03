"""Downloads posts from Substack's public endpoints.

Substack has no official API, but its website uses these two:

* /api/v1/archive?limit=12&offset=N   the list of posts, newest first
* /api/v1/posts/<slug>                one full post

They are not documented and could change, so the posts are saved to a file that the rest of the
project reads.
"""

import logging
import time

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from isaac_says.domain.models import RawPost

log = logging.getLogger(__name__)

PAGE_SIZE = 12  # bigger pages return fewer posts than asked for


def _is_retryable(error: BaseException) -> bool:
    """Retry network errors, rate limits (429) and server errors (5xx), but not 404."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code == 429 or error.response.status_code >= 500
    return isinstance(error, httpx.TransportError)


class SubstackClient:
    def __init__(
        self,
        publication: str,
        *,
        client: httpx.Client | None = None,
        delay_seconds: float = 0.25,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=f"https://{publication}.substack.com",
            headers={"User-Agent": "what-would-isaac-say/0.1 (personal project)"},
            timeout=30.0,
        )
        self._delay = delay_seconds  # a short pause between requests

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    def _get_json(self, url: str, **params: object) -> object:
        response = self._client.get(url, params=params or None)
        response.raise_for_status()
        time.sleep(self._delay)
        return response.json()

    def list_slugs(self) -> list[str]:
        """Go through the archive and return the slug of every post, newest first."""
        slugs: list[str] = []
        seen: set[int] = set()
        offset = 0
        while True:
            page = self._get_json("/api/v1/archive", sort="new", limit=PAGE_SIZE, offset=offset)
            if not isinstance(page, list) or not page:
                break  # an empty page means we reached the end
            for row in page:
                if row["id"] not in seen:  # the same post can appear on two pages
                    seen.add(row["id"])
                    slugs.append(row["slug"])
            offset += PAGE_SIZE
        log.info("Found %d posts in the archive", len(slugs))
        return slugs

    def fetch_post(self, slug: str) -> RawPost:
        """Download one full post."""
        return RawPost.model_validate(self._get_json(f"/api/v1/posts/{slug}"))

    def fetch_all(self) -> list[RawPost]:
        """Download every free newsletter post. Paid posts, podcasts and threads are skipped, so
        the assistant only quotes text that anyone can read."""
        posts: list[RawPost] = []
        for slug in self.list_slugs():
            post = self.fetch_post(slug)
            if post.audience != "everyone" or post.type != "newsletter":
                log.info("Skipping %s (audience=%s, type=%s)", slug, post.audience, post.type)
                continue
            posts.append(post)
        return sorted(posts, key=lambda p: p.post_date)
