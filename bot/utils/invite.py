import secrets
from bot.config import APP_BASE_URL

def generate_room_id():
    return secrets.token_urlsafe(8)

def build_invite_url(room_id: str) -> str:
    return f"{APP_BASE_URL.rstrip('/')}/app?room={room_id}"

