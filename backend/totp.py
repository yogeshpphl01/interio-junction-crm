"""
<module name="totp" layer="security">
  <purpose>
    Dependency-free RFC 6238 TOTP (HMAC-SHA1) for staff MFA — compatible with
    Google/Microsoft Authenticator, Authy, etc. No third-party lib so there is no
    supply-chain surface for the second factor. Replay is prevented by returning
    the matched time-step so the caller can reject any step already used
    (NIST 800-63B §5.2.8).
  </purpose>
</module>
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse
from typing import Optional

DIGITS = 6
PERIOD = 30  # seconds


def generate_secret(length_bytes: int = 20) -> str:
    """A base32 secret (>=160-bit) for authenticator apps."""
    return base64.b32encode(secrets.token_bytes(length_bytes)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    padding = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + padding)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(code).zfill(DIGITS)


def current_step(for_time: Optional[float] = None) -> int:
    return int((for_time if for_time is not None else time.time()) // PERIOD)


def verify(secret_b32: str, code: str, window: int = 1, for_time: Optional[float] = None) -> Optional[int]:
    """
    Verify a code against the current time step ±window. Returns the matched step
    (for replay tracking) or None. Constant-time compare.
    """
    code = (code or "").strip()
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(for_time)
    for w in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, step + w), code):
            return step + w
    return None


def provisioning_uri(secret_b32: str, account: str, issuer: str = "Interio Junction") -> str:
    """otpauth:// URI the app renders as a QR for enrollment."""
    label = urllib.parse.quote(f"{issuer}:{account}")
    params = urllib.parse.urlencode(
        {"secret": secret_b32, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD}
    )
    return f"otpauth://totp/{label}?{params}"
