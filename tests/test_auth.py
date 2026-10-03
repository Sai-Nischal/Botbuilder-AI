import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, User, Business
from app.security import hash_password, verify_password, sign_session, verify_session
from app.auth import verify_business_ownership
from fastapi import HTTPException


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_password_hashing():
    raw_pw = "SecurePass123!"
    pw_hash = hash_password(raw_pw)
    assert pw_hash != raw_pw
    assert verify_password(pw_hash, raw_pw) is True
    assert verify_password(pw_hash, "WrongPass") is False


def test_session_signing():
    user_id = 42
    signed_cookie = sign_session(user_id)
    assert signed_cookie is not None
    verified_id = verify_session(signed_cookie)
    assert verified_id == user_id

    # Tampered cookie
    tampered = signed_cookie[:-4] + "abcd"
    assert verify_session(tampered) is None


def test_business_ownership(db_session):
    user1 = User(email="owner1@test.com", password_hash="hash")
    user2 = User(email="owner2@test.com", password_hash="hash")
    db_session.add_all([user1, user2])
    db_session.commit()

    biz1 = Business(business_id="biz-101", owner_id=user1.id, name="Owner 1 Clinic")
    db_session.add(biz1)
    db_session.commit()

    # Owner 1 can access
    retrieved = verify_business_ownership(db_session, "biz-101", user1.id)
    assert retrieved.id == biz1.id

    # Owner 2 gets 404
    with pytest.raises(HTTPException) as exc_info:
        verify_business_ownership(db_session, "biz-101", user2.id)
    assert exc_info.value.status_code == 404
