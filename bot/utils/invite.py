import secrets
import json
import base64
from bot.config import APP_BASE_URL



def generate_room_id():
    return secrets.token_urlsafe(8)


def build_invite_url(room_id: str, user_info: dict = None) -> str:
    url = f"{APP_BASE_URL.rstrip('/')}/app?room={room_id}"
    if user_info:
        blob = base64.urlsafe_b64encode(json.dumps(user_info).encode()).decode()
        url += f"&u={blob}"
    return url

