"""
<module name="file_validation" layer="security">
  <purpose>
    Validate uploaded document bytes before they are stored/served (P1-10).
    We do NOT trust the client-declared content-type or the file extension:
    the actual bytes are sniffed against a curated allow-list, and the
    content-type we persist/serve is the SAFE one we derived — never the
    uploader's. This stops a renamed executable, and stops stored-XSS vectors
    (HTML / SVG-with-script / XML) from ever being served back inline.

    OWASP ASVS V12 (File & Resources), MASVS-CODE; Mobile M4; NIST SI-10;
    ISO A.8.26; CWE-434 (unrestricted upload), CWE-79 (stored XSS), CWE-646.
  </purpose>
</module>
"""
from fastapi import HTTPException

MAX_BYTES = 25 * 1024 * 1024  # keep in sync with the documents router cap

# Bytes that must NOT appear at the very start of any accepted upload — active
# content / executables, regardless of extension (defence in depth).
_DANGEROUS_PREFIXES = (
    b"MZ",            # Windows PE / .exe / .dll
    b"\x7fELF",       # Linux ELF
    b"#!",            # shebang script
    b"PK\x03\x04\x50\x4b",  # (only if later disallowed) — zip handled per-type
    b"<?php",
)
# Case-insensitive markers of markup/script that must never be stored as a
# "document" (they render as active content in a browser/WebView).
_MARKUP_MARKERS = (b"<script", b"<html", b"<!doctype html", b"<svg", b"<?xml", b"<iframe")


def _is_webp(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


# type-key -> (predicate(data)->bool, safe content-type, canonical extension)
_SIGNATURES = [
    ("pdf",  lambda d: d[:5] == b"%PDF-",                          "application/pdf",  "pdf"),
    ("png",  lambda d: d[:8] == b"\x89PNG\r\n\x1a\n",              "image/png",        "png"),
    ("jpg",  lambda d: d[:3] == b"\xff\xd8\xff",                   "image/jpeg",       "jpg"),
    ("gif",  lambda d: d[:6] in (b"GIF87a", b"GIF89a"),            "image/gif",        "gif"),
    ("webp", _is_webp,                                             "image/webp",       "webp"),
    ("dwg",  lambda d: d[:2] == b"AC" and d[2:4].isdigit(),        "image/vnd.dwg",    "dwg"),
]


def _looks_like_dxf(data: bytes) -> bool:
    """DXF is a text CAD format (no binary magic). Accept it only if the head is
    printable text that contains a DXF section marker and no NUL bytes."""
    head = data[:2048]
    if b"\x00" in head:
        return False
    try:
        text = head.decode("ascii", "ignore").upper()
    except Exception:
        return False
    return "SECTION" in text and ("HEADER" in text or "ENTITIES" in text or "TABLES" in text)


def validate_upload(filename: str, declared_content_type: str | None, data: bytes) -> tuple[str, str]:
    """Return (safe_content_type, canonical_extension) for an accepted upload, or
    raise HTTPException. `data` is the full file bytes."""
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")

    head = data[:64]
    lowered = data[:4096].lower()
    for marker in _MARKUP_MARKERS:
        if marker in lowered:
            raise HTTPException(status_code=415, detail="Markup/scriptable files are not allowed")
    for pre in _DANGEROUS_PREFIXES:
        if head.startswith(pre):
            raise HTTPException(status_code=415, detail="Executable or active-content files are not allowed")

    for _key, pred, safe_ct, ext in _SIGNATURES:
        try:
            if pred(data):
                return safe_ct, ext
        except Exception:
            continue
    if _looks_like_dxf(data):
        return "application/dxf", "dxf"

    raise HTTPException(
        status_code=415,
        detail="Unsupported file type — allowed: PDF, PNG, JPEG, GIF, WEBP, DWG, DXF",
    )


def safe_filename(name: str | None) -> str:
    """A display/download filename with no path separators, control chars or
    quotes (prevents Content-Disposition header injection and path tricks)."""
    base = (name or "file").replace("\\", "/").split("/")[-1]
    cleaned = "".join(c for c in base if c.isprintable() and c not in '"\r\n\t;')
    cleaned = cleaned.strip().strip(".") or "file"
    return cleaned[:180]
