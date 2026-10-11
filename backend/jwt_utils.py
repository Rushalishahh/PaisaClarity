import jwt
from datetime import datetime, timedelta, timezone

from config import get_secret_key

SECRET_KEY = get_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # token valid for 24 hours


def create_access_token(data: dict) -> str:
    """
    Create a signed JWT containing the given data (e.g. {'user_id': 5}).
    Adds an expiration time automatically.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """
    Verify and decode a JWT. Returns the payload dict if valid,
    or None if the token is invalid/expired/tampered with.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # token was valid but has expired
    except jwt.InvalidTokenError:
        return None  # token is malformed or signature doesn't match