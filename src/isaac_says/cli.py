"""The `isaac-says` command. Run `isaac-says --help` to see what it can do."""

import asyncio
import logging
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from isaac_says.logging_setup import configure_logging

app = typer.Typer(
    help="What Would Isaac Say? Tools for the newsletter assistant.", no_args_is_help=True
)
console = Console()


# Ingest and search
@app.command()
def ingest(
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Download the posts from Substack again first.")
    ] = False,
) -> None:
    """Build the search index. Use --refresh to pull new posts from Substack."""
    from isaac_says.config import get_settings
    from isaac_says.ingestion.pipeline import run_ingest
    from isaac_says.retrieval.embeddings import make_embeddings

    configure_logging()
    settings = get_settings()
    report = run_ingest(settings, make_embeddings(settings), refresh=refresh)
    console.print(
        f"[green]Done.[/green] {report.posts} posts, {report.chunks} chunks indexed, "
        f"{report.removed_stale} stale removed."
        + (" Snapshot refreshed from Substack." if report.downloaded else "")
    )


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="What to look for.")],
    k: Annotated[int, typer.Option("-k", help="How many results.")] = 5,
) -> None:
    """Search the index directly, without the model. Handy for checking what gets found."""
    from isaac_says.config import get_settings
    from isaac_says.retrieval.embeddings import make_embeddings
    from isaac_says.retrieval.index import VectorIndex

    configure_logging()
    settings = get_settings()
    index = VectorIndex(settings.chroma_dir, make_embeddings(settings))
    for r in index.search(query, k):
        console.print(
            f"[cyan]{r.score:.3f}[/cyan] [bold]{r.chunk.title}[/bold] > {r.chunk.heading}"
        )
        console.print(f"       {r.chunk.text[:160].replace(chr(10), ' ')}...", style="dim")


# Talking to the assistant
def _print_reply(reply) -> None:
    """Print a reply in the terminal."""
    if reply.kind == "answer":
        console.print(Panel(reply.text, title="Answer", border_style="green"))
        for c in reply.citations:
            where = c.url or "Isaac's direct answer"
            console.print(
                f'  [dim]-[/dim] [bold]{c.title}[/bold] > {c.heading}\n    "{c.quote}"\n    {where}'
            )
    elif reply.kind == "review":
        console.print(Panel(reply.summary, title="Review", border_style="blue"))
        for s in reply.strengths:
            console.print(f"  [green]+[/green] {s}")
        for issue in reply.issues:
            console.print(
                f"\n  [red]![/red] [bold]{issue.title}[/bold]\n    {issue.problem}\n    [green]Try:[/green] {issue.advice}"
            )
            console.print(f'    [dim]From "{issue.citation.title}": "{issue.citation.quote}"[/dim]')
        console.print(f"\n  [bold]Next step:[/bold] {reply.next_step}")
    elif reply.kind == "needs_input":
        console.print(Panel(reply.question, title="I need one more detail", border_style="yellow"))
    else:  # not_covered and chitchat both carry plain text
        console.print(
            Panel(reply.text, border_style="magenta" if reply.kind == "not_covered" else "white")
        )


async def _run_chat(messages: list[str] | None) -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    from isaac_says.agent.factory import build_chat_service
    from isaac_says.config import get_settings

    service, _ = build_chat_service(get_settings(), checkpointer=InMemorySaver())
    thread_id: str | None = None

    async def turn(text: str) -> None:
        nonlocal thread_id
        result = await service.run_turn(thread_id, text)
        thread_id = result.thread_id
        _print_reply(result.reply)
        console.print(
            f"[dim]{result.latency_ms} ms, {result.usage.input_tokens + result.usage.output_tokens} tokens, "
            f"${result.usage.cost_usd:.4f}[/dim]"
        )

    if messages:
        for text in messages:
            console.print(f"\n[bold]> {text}[/bold]")
            await turn(text)
        return
    console.print("Type a question, or describe your work for a review. Empty line to quit.")
    while text := console.input("\n[bold]> [/bold]").strip():
        await turn(text)


@app.command()
def ask(question: Annotated[str, typer.Argument(help="Your question.")]) -> None:
    """Ask one question and print the answer."""
    configure_logging(logging.WARNING)
    asyncio.run(_run_chat([question]))


@app.command()
def chat() -> None:
    """Start an interactive conversation in the terminal."""
    configure_logging(logging.WARNING)
    asyncio.run(_run_chat(None))


# Housekeeping
@app.command("purge-threads")
def purge_threads(
    days: Annotated[
        int | None,
        typer.Option(
            help="Delete conversations idle longer than this (default: THREAD_RETENTION_DAYS)."
        ),
    ] = None,
) -> None:
    """Delete stored conversations that have been idle past the retention period."""
    from isaac_says.config import get_settings
    from isaac_says.db.retention import purge_stale_threads

    configure_logging(logging.WARNING)
    removed = asyncio.run(purge_stale_threads(get_settings(), days))
    console.print(f"Deleted {removed} idle conversation(s).")


# Servers
@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: Annotated[
        bool, typer.Option(help="Restart on code changes (development only).")
    ] = False,
) -> None:
    """Run the HTTP API. Docs appear at http://HOST:PORT/docs"""
    import uvicorn

    uvicorn.run("isaac_says.api.main:app", host=host, port=port, reload=reload)


@app.command()
def mcp() -> None:
    """Run the MCP server, so Claude Desktop and other apps can use the newsletter."""
    from isaac_says.mcp_server import main

    main()


if __name__ == "__main__":
    app()
