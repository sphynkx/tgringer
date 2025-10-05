from fastapi import APIRouter
import secrets
from server.config import APP_BASE_URL

router = APIRouter()



@router.get("/invite/new")
async def new_invite():
    room_id = secrets.token_urlsafe(8)
    url = f"{APP_BASE_URL.rstrip('/')}/app?room={room_id}"
    return {
        "roomId": room_id,
        "url": url,
        "tg_web_app_url": url
    }

