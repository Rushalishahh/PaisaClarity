from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from database import get_db
from models import User
from jwt_utils import decode_access_token


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Extracts and verifies the JWT from the Authorization header,
    then fetches the corresponding user from the database.
    Any protected route can require this by adding it as a dependency.
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")

    return user