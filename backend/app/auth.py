"""JWT and Password Authentication Helpers for NM-HireX.

This module provides authentication, password hashing, and role-based access control (RBAC):
1. Password Security: Uses `bcrypt` with automated salt generation for secure password hashing and verification.
2. Token Lifecycle: Issues signed JWT access tokens containing user identity (`sub`), email, role, and expiration.
3. Fast-API Dependencies:
   - `get_current_user`: Validates incoming Bearer JWT tokens, decodes payload, and retrieves the active user.
   - `require_admin`: Enforces administrative privileges for protected admin-only routes.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

# OAuth2 password bearer scheme that extracts Bearer token from the 'Authorization' header.
# Points to the login endpoint URL for OpenAPI/Swagger UI integration.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with a securely generated salt.

    Detailed Functionality:
    - Encodes the password string to UTF-8 bytes.
    - Generates a random salt using `bcrypt.gensalt()`.
    - Hashes the password and decodes the resulting hash back to a UTF-8 string for DB storage.

    Parameters:
        password (str): Plaintext password to hash.

    Returns:
        str: Bcrypt hashed password string suitable for database storage.

    Raises:
        ValueError: If the provided password is empty or None.
    """
    if not password:
        raise ValueError("Password cannot be empty")
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash in constant time.

    Detailed Functionality:
    - Checks for non-empty input strings.
    - Uses `bcrypt.checkpw()` to prevent timing attacks.
    - Catches any encoding or format errors safely and returns False on invalid input.

    Parameters:
        plain_password (str): Plaintext candidate password provided during login.
        hashed_password (str): Stored bcrypt hash string from the database.

    Returns:
        bool: True if password matches the hash, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    """Create a signed JWT access token for an authenticated user.

    Detailed Functionality:
    - Computes expiration timestamp in UTC using `settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES`.
    - Embeds claims:
      * 'sub': String representation of user UUID.
      * 'email': User email address.
      * 'role': User system role ('ADMIN', 'RECRUITER').
      * 'exp': Expiration timestamp.
    - Signs token using `settings.JWT_SECRET_KEY` with algorithm `settings.JWT_ALGORITHM`.

    Parameters:
        user (User): Authenticated User database model instance.

    Returns:
        str: Encoded, signed JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency to extract and authenticate the current user from the Bearer JWT token.

    Detailed Functionality:
    - Extracts token from `Authorization: Bearer <token>` header via `oauth2_scheme`.
    - Decodes and validates signature and expiration using `JWT_SECRET_KEY`.
    - Extracts subject (`sub`) claim and parses as UUID.
    - Queries database for the User record.
    - Checks that user exists and is active (`user.is_active == True`).

    Parameters:
        token (str): Injected Bearer token string.
        db (Session): Injected SQLAlchemy database session.

    Returns:
        User: The authenticated User SQLAlchemy model instance.

    Raises:
        HTTPException(401): If token is invalid, expired, missing 'sub', or user not found.
        HTTPException(403): If the user account has been deactivated (`is_active=False`).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception
        user_uuid = UUID(str(user_id))
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.get(User, user_uuid)
    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI authorization dependency ensuring the current user has the 'ADMIN' role.

    Detailed Functionality:
    - Depends on `get_current_user` to ensure user is authenticated and active.
    - Verifies that `user.role == "ADMIN"`.
    - Blocks recruiters or standard users from accessing administrative resources.

    Parameters:
        user (User): Authenticated user injected from `get_current_user`.

    Returns:
        User: Authenticated administrator User instance.

    Raises:
        HTTPException(403): If user does not have the 'ADMIN' role.
    """
    if user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
