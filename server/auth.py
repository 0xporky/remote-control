from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

import config

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token scheme
security = HTTPBearer()


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class LoginRequest(BaseModel):
    password: str


class GoogleLoginRequest(BaseModel):
    credential: str  # The Google ID token


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """Verify a JWT token and return token data."""
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return TokenData(username=username)
    except JWTError:
        return None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """Dependency to get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_token(credentials.credentials)
    if token_data is None:
        raise credentials_exception
    return token_data


def authenticate(password: str) -> bool:
    """Authenticate using the configured password."""
    if config.AUTH_PASSWORD is None:
        return False
    return password == config.AUTH_PASSWORD


def verify_google_token(token: str) -> Optional[dict]:
    """Verify a Google ID token and return user info."""
    if not config.GOOGLE_CLIENT_ID:
        return None
    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            config.GOOGLE_CLIENT_ID
        )

        # Check if issuer is Google
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            return None

        return {
            'email': idinfo['email'],
            'email_verified': idinfo.get('email_verified', False),
            'name': idinfo.get('name', ''),
            'picture': idinfo.get('picture', ''),
        }
    except ValueError:
        return None


def is_google_user_allowed(email: str) -> bool:
    """Check if Google user is allowed to access the application."""
    # If no restrictions configured, allow all verified Google accounts
    if not config.GOOGLE_ALLOWED_DOMAINS and not config.GOOGLE_ALLOWED_EMAILS:
        return True

    # Check email allowlist
    if email in config.GOOGLE_ALLOWED_EMAILS:
        return True

    # Check domain allowlist
    domain = email.split('@')[-1]
    if domain in config.GOOGLE_ALLOWED_DOMAINS:
        return True

    return False
