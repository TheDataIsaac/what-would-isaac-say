"""Style cleanup for the assistant's own text. Quotes from the newsletter are never changed."""

import re

# An em dash or en dash, with any spaces around it.
_SPACED_DASH = re.compile(r"\s*[—–]\s*")


def clean_prose(text: str) -> str:
    """Replace em and en dashes with a spaced hyphen."""
    return _SPACED_DASH.sub(" - ", text).strip()
