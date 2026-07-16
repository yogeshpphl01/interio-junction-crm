"""
<module name="auth_utils" layer="security">
  <purpose>Password hashing (bcrypt), JWT access/refresh tokens, and the auth
  cookie helpers used by the auth router and the get_current_user dependency.</purpose>
  <tokens>
    access  : 8h TTL, carries sub/email/role, type="access".
    refresh : 7d TTL, carries sub, type="refresh".
    Secret comes from the JWT_SECRET environment variable.
  </tokens>
  <token-extraction>extract_token() prefers the httpOnly cookie, then falls back
  to an "Authorization: Bearer ..." header (some preview hosts drop cookies).</token-extraction>
</module>
"""
import os
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request, Response

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MIN = 60 * 8  # 8 hours, friendly for CRM use
REFRESH_TOKEN_TTL_DAYS = 7


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


_WEAK_SECRETS = {"", "x", "secret", "changeme", "change-me", "dev", "devsecret",
                 "password", "test", "test-secret", "test-secret-booking", "jwt", "supersecret"}


def validate_security_config() -> None:
    """
    Fail fast on missing/weak security config in production (NIST SC-12 / CWE-798).
    In non-prod we only warn, so local dev with a throwaway secret still runs.
    """
    import logging
    log = logging.getLogger("security")
    prod = os.environ.get("APP_ENV", "").lower() in ("prod", "production")
    secret = os.environ.get("JWT_SECRET", "")
    if prod:
        if len(secret) < 32 or secret.lower() in _WEAK_SECRETS:
            raise RuntimeError("JWT_SECRET must be a strong random value (>= 32 chars) in production")
        if not (os.environ.get("DATABASE_URL") or os.environ.get("PG_HOST")):
            raise RuntimeError("Database connection is not configured (DATABASE_URL / PG_HOST)")
        if os.environ.get("OTP_DEBUG_LOG"):
            log.warning("OTP_DEBUG_LOG is set but ignored in production (codes are never logged)")
    elif len(secret) < 16 or secret.lower() in _WEAK_SECRETS:
        log.warning("JWT_SECRET is weak/short — use a strong random value (fine for local dev only)")


def otp_debug_logging() -> bool:
    """
    DEV-ONLY: whether plaintext OTP / reset codes may be written to the server log.
    Off unless OTP_DEBUG_LOG is truthy, and force-off in production (APP_ENV=prod).
    Codes are secrets and must never reach logs in production
    (OWASP MASVS-STORAGE / NIST 800-53 AU-9 / CWE-532).
    """
    if os.environ.get("APP_ENV", "").lower() in ("prod", "production"):
        return False
    return os.environ.get("OTP_DEBUG_LOG", "").lower() in ("1", "true", "yes", "on")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


MFA_PENDING_TTL_MIN = 5  # short window to complete the second factor after password


def create_access_token(user_id: str, email: str, role: str, aal: int = 1, amr=None, tv: int = 0) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_TTL_MIN),
        "type": "access",
        "aal": aal,                       # NIST 800-63B authenticator assurance level (1 or 2)
        "amr": amr or ["pwd"],            # auth methods used (e.g. ["pwd","otp"])
        "tv": tv,                         # token version — bump on the user to revoke
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_mfa_pending_token(user_id: str) -> str:
    """Issued after a correct password when MFA is enrolled; only /auth/mfa/verify
    accepts it. Grants no access on its own."""
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=MFA_PENDING_TTL_MIN),
        "type": "mfa_pending",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


STEP_UP_TTL_MIN = 5  # elevation window for a sensitive action after a fresh 2nd factor


def create_step_up_token(user_id: str) -> str:
    """Short-lived proof of a fresh second factor, for step-up on sensitive actions."""
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=STEP_UP_TTL_MIN),
        "type": "step_up",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_customer_step_up_token(customer_id: str) -> str:
    """Short-lived elevation for a Client-App customer after a fresh on-device
    biometric/PIN check, for high-risk actions (accept estimate, approve design)."""
    payload = {
        "sub": customer_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=STEP_UP_TTL_MIN),
        "type": "customer_step_up",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, tv: int = 0) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
        "type": "refresh",
        "tv": tv,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


DOC_URL_TTL_MIN = 5  # a signed document URL is a short-lived capability


def create_doc_download_token(doc_id: str, subject: str, audience: str, ttl_min: int = DOC_URL_TTL_MIN) -> str:
    """A signed, short-lived capability to download ONE document (P1-10). Bound to
    the doc id and the requesting subject (a user or a customer id) + audience, so
    a leaked link expires quickly and cannot be repointed at another document."""
    payload = {
        "sub": subject,
        "doc": doc_id,
        "aud_kind": audience,             # "staff" | "customer" — which world minted it
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ttl_min),
        "type": "doc_download",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


# ---- Client App (customer) tokens -----------------------------------------
# A SEPARATE token family for the Client App. The distinct "customer_access"
# type is the dual-BFF security boundary: get_current_user rejects anything
# whose type != "access", and get_current_customer rejects anything whose type
# != "customer_access" — so an employee token can never reach a customer
# endpoint and a customer token can never reach a company/RBAC endpoint. Mobile
# clients keep a long-lived refresh so customers rarely re-authenticate.
CUSTOMER_ACCESS_TTL_MIN = 60 * 24        # 24h
CUSTOMER_REFRESH_TTL_DAYS = 60


def create_customer_access_token(customer_id: str, phone: str, tv: int = 0) -> str:
    payload = {
        "sub": customer_id,
        "phone": phone,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=CUSTOMER_ACCESS_TTL_MIN),
        "type": "customer_access",
        "tv": tv,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_customer_refresh_token(customer_id: str, tv: int = 0) -> str:
    payload = {
        "sub": customer_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=CUSTOMER_REFRESH_TTL_DAYS),
        "type": "customer_refresh",
        "tv": tv,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=ACCESS_TOKEN_TTL_MIN * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def extract_token(request: Request) -> str:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token
