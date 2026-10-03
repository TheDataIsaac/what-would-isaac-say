"""Saves the downloaded posts to a file, one post per line, so the index can be rebuilt offline."""

from pathlib import Path

from isaac_says.domain.models import RawPost


def save_snapshot(posts: list[RawPost], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for post in posts:
            f.write(post.model_dump_json() + "\n")


def load_snapshot(path: Path) -> list[RawPost]:
    if not path.exists():
        raise FileNotFoundError(
            f"No snapshot at {path}. Run `isaac-says ingest --refresh` to download the posts."
        )
    with path.open(encoding="utf-8") as f:
        return [RawPost.model_validate_json(line) for line in f if line.strip()]
