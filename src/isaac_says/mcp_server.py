"""An MCP server that lets other apps list, read and search the newsletter posts.

Run it with `isaac-says mcp`. To add it to Claude Desktop, put this in claude_desktop_config.json:

    {"mcpServers": {"explain-the-data": {
        "command": "uv",
        "args": ["--directory", "/path/to/what-would-isaac-say", "run", "isaac-says", "mcp"]}}}

The tool descriptions are read by the other app's model, so keep them clear. Do not print() here,
because the output is how the server talks to the app.
"""

from functools import lru_cache

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from isaac_says.config import get_settings
from isaac_says.domain.models import RawPost
from isaac_says.ingestion.cleaning import html_to_sections
from isaac_says.ingestion.snapshot import load_snapshot

mcp = MCPServer(
    "explain-the-data",
    instructions=(
        "Posts from Isaac Oresanya's 'Explain the Data' newsletter about charts, dashboards, "
        "reports, SQL and analyst careers. Use search_posts to find relevant passages, get_post "
        "to read a whole post, and list_posts to browse."
    ),
)


@lru_cache
def _posts() -> dict[str, RawPost]:
    """Load the saved posts once, as a dict keyed by slug."""
    return {p.slug: p for p in load_snapshot(get_settings().snapshot_path)}


@mcp.tool()
def list_posts(tag: str | None = None, limit: int = 20) -> list[dict]:
    """List newsletter posts, newest first. Optionally filter by a tag such as 'Dashboard'."""
    posts = sorted(_posts().values(), key=lambda p: p.post_date, reverse=True)
    if tag:
        posts = [p for p in posts if tag.lower() in (t.lower() for t in p.tags)]
    return [
        {
            "slug": p.slug,
            "title": p.title,
            "subtitle": p.subtitle,
            "published": p.post_date.date().isoformat(),
            "tags": p.tags,
            "url": p.canonical_url,
        }
        for p in posts[: max(1, min(limit, 100))]
    ]


@mcp.tool()
def get_post(slug: str) -> str:
    """Return the full text of one post, given its slug (from list_posts or search_posts)."""
    post = _posts().get(slug)
    if post is None:
        # ToolError sends this message back to the caller, who can fix it and try again.
        raise ToolError(f"No post with slug '{slug}'. Use list_posts to see valid slugs.")
    lines = [
        f"# {post.title}",
        f"Published {post.post_date.date().isoformat()} | {post.canonical_url}",
        "",
    ]
    for section in html_to_sections(post):
        lines += [f"## {section.heading}", section.text, ""]
    return "\n".join(lines)


@mcp.tool()
def search_posts(query: str, k: int = 5) -> list[dict]:
    """Search the newsletter by meaning. Returns the best matching passages and where they are from.

    Use it for questions like 'what does Isaac say about dual axis charts?'. It needs the search
    index (run `isaac-says ingest` first) and an OpenAI key.
    """
    # Imported here, so list_posts and get_post work without an OpenAI key or a search index.
    from isaac_says.retrieval.embeddings import make_embeddings
    from isaac_says.retrieval.index import VectorIndex

    settings = get_settings()
    index = VectorIndex(settings.chroma_dir, make_embeddings(settings))
    return [
        {
            "score": r.score,
            "title": r.chunk.title,
            "heading": r.chunk.heading,
            "url": r.chunk.url,
            "slug": r.chunk.post_slug,
            "text": r.chunk.text,
        }
        for r in index.search(query, max(1, min(k, 20)))
    ]


@mcp.resource("post://{slug}")
def post_resource(slug: str) -> str:
    """The same text as get_post, as a resource that an app can attach to a chat."""
    return get_post(slug)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
