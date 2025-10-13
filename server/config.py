import os
from dotenv import load_dotenv

load_dotenv()

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:91")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TURN_URLS = [u.strip() for u in os.getenv("TURN_URLS", "stun:stun.l.google.com:19302").split(",") if u.strip()]
TURN_USERNAME = os.getenv("TURN_USERNAME") or ""
TURN_PASSWORD = os.getenv("TURN_PASSWORD") or ""
