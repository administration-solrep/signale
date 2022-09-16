import re
import threading
import unicodedata
from html import unescape

from bleach.sanitizer import Cleaner

ALLOWED_TAGS = [
    "div",
    "p",
    "h3",
    "ul",
    "ol",
    "li",
    "b",
    "i",
    "strong",
    "em",
    "sub",
    "sup",
    "table",
    "thead",
    "th",
    "tbody",
    "tr",
    "td",
    # Useful to be able to clean diffs in journals.
    "ins",
    "del",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "abbr": ["title"],
    "acronym": ["title"],
    "td": ["colspan"],
    "th": ["colspan"],
}

TINYMCE_ATTRIBUTES_CSS = {
    "a": ["href", "title"],
    "abbr": ["title"],
    "acronym": ["title"],
    "table": ["style"],
    "tr": ["style"],
    "td": ["colspan", "style"],
    "th": ["colspan", "style"],
    "p": ["style"],
    "li": ["style"],
    "ul": ["style"],
    "ol": ["style"],
    "h3": ["style"],
    "div": ["style"],
}

TINYMCE_STYLES = ["text-align"]

ALLOWED_TABLE_TAGS = ["table", "thead", "th", "tbody", "tr", "td", "tfoot", "p", "br"]

ALLOWED_TABLE_ATTRIBUTES = {
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}

ALLOWED_PARSER_ATTRIBUTES = {
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    "p": ["class"],
}


# Bleach uses html5lib, which is not thread-safe, so we have to use a cleaner instance
# per thread instead of a global one to avoid transient errors in our workers
#
# See: https://github.com/mozilla/bleach/issues/370
#
_THREAD_LOCALS = threading.local()


def clean_html(html: str) -> str:
    text = unescape(html)  # decode HTML entities

    if not hasattr(_THREAD_LOCALS, "cleaner"):
        _THREAD_LOCALS.cleaner = Cleaner(
            tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True
        )

    sanitized: str = _THREAD_LOCALS.cleaner.clean(text)
    return sanitized.strip()


def clean_tinymce(html: str) -> str:
    text = unescape(html)  # decode HTML entities

    if not hasattr(_THREAD_LOCALS, "cleaner_css"):
        _THREAD_LOCALS.cleaner_css = Cleaner(
            tags=ALLOWED_TAGS,
            attributes=TINYMCE_ATTRIBUTES_CSS,
            styles=TINYMCE_STYLES,
            strip=True,
        )

    sanitized: str = _THREAD_LOCALS.cleaner_css.clean(text)
    return sanitized.strip()


def clean_all_html(html: str) -> str:
    text = unescape(html)  # decode HTML entities
    if not hasattr(_THREAD_LOCALS, "cleaner_all"):
        _THREAD_LOCALS.cleaner_all = Cleaner(tags=[], strip=True)

    sanitized: str = _THREAD_LOCALS.cleaner_all.clean(text)
    return sanitized.strip()


def clean_all_for_search(html: str) -> str:
    # We do an unescape here due to cleaner behavior
    text = unescape(clean_all_html(html))  # decode HTML entities

    # clean blancs insécable
    text = text.replace(u"\xa0", u" ")
    return text


def clean_html_except_tables(html: str) -> str:
    text = unescape(html)  # decode HTML entities

    if not hasattr(_THREAD_LOCALS, "cleaner_except_tables"):
        _THREAD_LOCALS.cleaner_except_tables = Cleaner(
            tags=ALLOWED_TABLE_TAGS, attributes=ALLOWED_TABLE_ATTRIBUTES, strip=True
        )

    sanitized: str = _THREAD_LOCALS.cleaner_except_tables.clean(text)
    return sanitized.strip()


def clean_parser_except_tables(html: str) -> str:
    text = unescape(html)  # decode HTML entities

    if not hasattr(_THREAD_LOCALS, "cleaner_parser_except_tables"):
        _THREAD_LOCALS.cleaner_parser_except_tables = Cleaner(
            tags=ALLOWED_TABLE_TAGS + ["img"],
            attributes=ALLOWED_PARSER_ATTRIBUTES,
            strip=True,
        )

    sanitized: str = _THREAD_LOCALS.cleaner_parser_except_tables.clean(text)
    return sanitized.strip()


def clean_characters(chaine: str, regex: str) -> str:
    texte = re.sub(regex, "", chaine)
    return texte.strip()


def clean_line_break_br(chaine: str) -> str:
    texte = chaine.replace("<br>", " ")
    return texte.replace("&lt;br&gt;", " ")


def clean_line_break_n(chaine: str) -> str:
    return chaine.replace("\n", "")


def clean_special_car(chaine: str) -> str:
    if chaine[-3:] == ". –":
        return chaine.replace(". –", "")
    return chaine


def clean_mention(chaine: str, mention: str) -> str:
    return chaine.replace(" " + mention, "")


def clean_mention_at_end(chaine: str, mention: str) -> str:
    taille_mention = len(mention)
    if chaine[-taille_mention:] == mention:
        return clean_mention(chaine, mention)
    return chaine


def clean_accents(chaine: str) -> str:
    return str(
        unicodedata.normalize("NFKD", chaine).encode("ASCII", "ignore").decode("utf-8")
    )


def encode_special_car(chaine: str) -> str:
    return chaine.replace("%", "\\%").replace("_", "\\_")


def decode_special_car(chaine: str) -> str:
    return chaine.replace("\\%", "%").replace("\\_", "_")
