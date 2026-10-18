import uuid
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if credentials is None:
        raise HTTPException(401, "Authentication required.")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        subject = uuid.UUID(payload.get("sub", ""))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(401, "Invalid or expired access token.")
    user = db.query(User).filter(User.id == subject).first()
    if not user or not user.is_active or not user.email_verified:
        raise HTTPException(401, "User is unavailable or not verified.")
    return user
