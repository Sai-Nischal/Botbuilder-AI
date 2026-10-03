#!/usr/bin/env python3
import uvicorn
from app.config import DEBUG

if __name__ == "__main__":
    print("Starting BotBuilder Web Application Server...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=DEBUG)
