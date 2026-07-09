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


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_TTL_MIN),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
        "type": "refresh",
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


def create_customer_access_token(customer_id: str, phone: str) -> str:
    payload = {
        "sub": customer_id,
        "phone": phone,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=CUSTOMER_ACCESS_TTL_MIN),
        "type": "customer_access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_customer_refresh_token(customer_id: str) -> str:
    payload = {
        "sub": customer_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=CUSTOMER_REFRESH_TTL_DAYS),
        "type": "customer_refresh",
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
