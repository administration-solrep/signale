import re
from typing import Any, Optional

from zam_repondeur.models import User

SLUG_REGEX = re.compile("""^[-\w]+$""")  # noqa: W605

SANITIZE = (
    (";", ""),
    (" select ", " "),
    ("select ", " "),
    (" update ", " "),
    (" insert ", " "),
    (" delete ", " "),
    (" from ", " "),
    ("--", ""),
    ("#", ""),
)


def get_as_int_or_none(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def get_as_slug_or_none(raw: str) -> Optional[str]:
    if SLUG_REGEX.match(raw):
        return raw
    return None


def get_as_email_or_none(raw: str) -> Optional[str]:
    if User.email_is_well_formed(raw):
        return raw
    return None


def sanitize_string(raw: str) -> str:
    clean = raw.lower()
    for search, replacement in SANITIZE:
        clean = clean.replace(search, replacement)
    return clean
