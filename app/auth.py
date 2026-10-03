from typing import Optional
from fastapi import Request, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.db import User, Business, get_db
from app.security import verify_session, hash_password, verify_password, sign_session, generate_csrf_token, verify_csrf_token

SESSION_COOKIE_NAME = "botbuilder_session"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_val:
        return None
    user_id = verify_session(cookie_val)
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )
    return user


def verify_business_ownership(db: Session, business_id: str, user_id: int) -> Business:
    business = db.query(Business).filter(
        Business.business_id == business_id,
        Business.owner_id == user_id
    ).first()
    
    if not business:
        # Crucial requirement: return 404 for non-existent or other user's business
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )
    return business


def check_csrf(request: Request):
    session_val = request.cookies.get(SESSION_COOKIE_NAME, "")
    csrf_token = request.headers.get("X-CSRF-Token")
    
    # Check form body if not in header
    if not csrf_token:
        # Form body checking will be handled in route handlers if async body is parsed
        pass
