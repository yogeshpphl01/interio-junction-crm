"""
<module name="pii_crypto" layer="security">
  <purpose>
    Application-layer field encryption for PII at rest (P2 / control C6). The
    stored value is encrypted with AES-256-GCM (randomised — the same plaintext
    yields different ciphertext each time), and a separate deterministic
    HMAC-SHA256 "blind index" is kept alongside so equality lookups and UNIQUE
    constraints on phone/email still work. This is the standard encrypted-column
    + blind-index pattern (see THREAT_MODEL.md §5).

    OWASP MASVS-STORAGE / ASVS V6; NIST SC-28; ISO A.8.11; DPDP §8.
  </purpose>
  <safety>
    Opt-in + backward compatible. Disabled (PII_ENCRYPTION_KEY unset) -> the
    functions are no-ops and the shim stores plaintext exactly as before. Enabled
    -> values are encrypted on write and decrypted on read; `decrypt()` returns
    any non-`pii1:` value unchanged, so legacy plaintext rows keep working until
    the one-shot `migrate_pii.py` backfills them.

    KEY: PII_ENCRYPTION_KEY is a base64-encoded 32-byte master key. In production
    load it from a KMS / Secret Manager (envelope encryption) rather than a raw
    env var — the loader below is the single integration point to swap.
  </safety>
</module>
"""
import os
import hmac
import base64
import hashlib
from functools import lru_cache

PREFIX = "pii1:"           # marks our ciphertext so decrypt() can detect/skip
_NONCE_LEN = 12


def _master_key() -> bytes | None:
    raw = os.environ.get("PII_ENCRYPTION_KEY")
    if not raw:
        return None
    try:
        key = base64.b64decode(raw)
    except Exception:
        return None
    return key if len(key) == 32 else None


def pii_enabled() -> bool:
    return _master_key() is not None


@lru_cache(maxsize=1)
def _subkeys() -> tuple[bytes, bytes]:
    """Derive independent encryption + blind-index keys from the master key."""
    master = _master_key() or b""
    enc = hmac.new(master, b"ij-pii-enc-v1", hashlib.sha256).digest()
    idx = hmac.new(master, b"ij-pii-idx-v1", hashlib.sha256).digest()
    return enc, idx


def _aesgcm():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # requires cryptography
    return AESGCM(_subkeys()[0])


def encrypt(plaintext: str) -> str:
    """AES-256-GCM encrypt -> 'pii1:' + base64(nonce || ciphertext||tag). No-op
    (returns the input) when disabled or already encrypted."""
    if plaintext is None or not pii_enabled() or (isinstance(plaintext, str) and plaintext.startswith(PREFIX)):
        return plaintext
    nonce = os.urandom(_NONCE_LEN)
    ct = _aesgcm().encrypt(nonce, str(plaintext).encode("utf-8"), None)
    return PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt(value: str) -> str:
    """Reverse encrypt(). Any value without our prefix (plaintext / legacy row)
    is returned unchanged, so mixed states work during migration."""
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    if not pii_enabled():
        return value  # can't decrypt without the key; leave as-is
    try:
        blob = base64.b64decode(value[len(PREFIX):])
        nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
        return _aesgcm().decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return value


def blind_index(plaintext: str) -> str | None:
    """Deterministic HMAC-SHA256 of the value — the searchable/UNIQUE surrogate
    for an encrypted column. Callers must pass the already-normalised value
    (e.g. last-10-digit phone, lower-cased email) so writes and lookups agree."""
    if plaintext is None or not pii_enabled():
        return None
    return hmac.new(_subkeys()[1], str(plaintext).encode("utf-8"), hashlib.sha256).hexdigest()
