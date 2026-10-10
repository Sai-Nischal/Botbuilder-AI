from app.db import SessionLocal, User
db = SessionLocal()
try:
    user = db.query(User).first()
    if user:
        print(f"User found: {user.email}, Username: {user.username}")
    else:
        print("No users found in DB")
except Exception as e:
    print(f"DB Error: {e}")
finally:
    db.close()
