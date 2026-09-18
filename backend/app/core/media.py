"""What an upload is allowed to be, and how that is checked.

Pure functions over bytes and strings, so the rules can be tested without a database, a bucket or
an HTTP request — and so the same rules apply whichever storage driver is running.

**An allow-list, never a deny-list.** A restaurant uploads photographs and occasionally a PDF
invoice. Everything else is refused before a key is issued. A deny-list of dangerous types is a
list somebody has to keep up to date against an attacker who does not have to.

**The declared type is a claim; the first bytes are the evidence.** With a presigned upload the
bytes never pass through this process, so a content type in a request body is something a client
said. `matches_signature` is what turns it into something we checked — and it runs against the
object as the *store* has it, not against the request.

Note what is deliberately absent: no HTML, no SVG, no JavaScript, no archive format. SVG is the
one a reader should look twice at — it is an image to a person and a script to a browser, which is
exactly the stored-XSS the separate-origin rule exists to prevent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# How many bytes `matches_signature` needs. Twelve would do for everything but HEIC, whose brand
# lives at offset 8; sixteen is the next round number and costs nothing.
SIGNATURE_BYTES = 16

# The allow-list, and the reason each one is on it.
ALLOWED_CONTENT_TYPES: Mapping[str, str] = {
    "image/jpeg": ".jpg",  # every phone camera
    "image/png": ".png",  # a screenshot of a supplier's message
    "image/webp": ".webp",  # what some Android cameras and browsers produce
    "image/heic": ".heic",  # what an iPhone produces by default
    "application/pdf": ".pdf",  # a supplier's invoice
}

# Magic numbers, as the format specifications give them.
_PREFIXES: Mapping[str, Sequence[bytes]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "application/pdf": (b"%PDF-",),
}

# HEIC and WebP are both ISO-style container formats: a length, a box name, then a brand. Checking
# only the outer prefix would accept any RIFF file as a WebP and any MP4 as a HEIC.
_WEBP_RIFF = b"RIFF"
_WEBP_FORM = b"WEBP"
_HEIF_BOX = b"ftyp"
# The brands a camera actually writes. `mif1`/`msf1` are the generic image and sequence brands;
# `heic`/`heix`/`hevc`/`hevx` are the HEVC-coded ones.
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")


def is_allowed(content_type: str) -> bool:
    return content_type in ALLOWED_CONTENT_TYPES


def extension_for(content_type: str) -> str:
    """The extension the generated key ends with. Never taken from the uploaded filename."""
    return ALLOWED_CONTENT_TYPES.get(content_type, "")


def matches_signature(content_type: str, head: bytes) -> bool:
    """Do these first bytes look like the type that was declared?

    Returns False for an unknown type as well as a mismatched one: a type that is not on the
    allow-list has no signature to match, and answering True would make this function a way round
    `is_allowed` rather than a second check after it.
    """
    if content_type == "image/webp":
        return len(head) >= 12 and head[:4] == _WEBP_RIFF and head[8:12] == _WEBP_FORM
    if content_type == "image/heic":
        return len(head) >= 12 and head[4:8] == _HEIF_BOX and head[8:12] in _HEIF_BRANDS
    prefixes = _PREFIXES.get(content_type)
    if prefixes is None:
        return False
    return any(head.startswith(prefix) for prefix in prefixes)


def safe_file_name(raw: str) -> str:
    """A display string, never a path.

    The stored key is generated, so this cannot become a traversal — but the name is rendered in a
    browser and echoed in a `Content-Disposition`, so the separators go, the control characters go,
    and the length is bounded. An empty result becomes a placeholder rather than an empty header.
    """
    cleaned = "".join(
        character for character in raw if character.isprintable() and character not in '\\/\r\n"'
    ).strip()
    # Leading dots make a file hidden on unix and are how "..", ".." and ".env" get interesting.
    cleaned = cleaned.lstrip(".")
    return cleaned[:120] or "attachment"
