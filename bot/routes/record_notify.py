## Bot recording notification routes (owner delivery)
## No async context manager for Bot; absolute URL build; allow webm/mp4; ASCII-only comments.

import os
import re
from fastapi import APIRouter, Request, HTTPException
from aiogram import Bot
from bot.config import APP_BASE_URL

router = APIRouter()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
_URL_RE = re.compile(r"^(?:https?://.+|/static/records/.+\.(?:webm|mp4))$", re.IGNORECASE)


def _absolute_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = (APP_BASE_URL or "").rstrip("/")
    if not base:
        return url
    if url.startswith("/"):
        return f"{base}{url}"
    return f"{base}/{url}"


def _build_message(room_id: str, file_url: str) -> str:
    return (
        f"<b>Recording finished</b>\n"
        f"Room: <code>{room_id}</code>\n"
        f"File: <a href=\"{file_url}\">{file_url}</a>"
    )


@router.post("/bot/send_record")
async def bot_send_record(request: Request):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    room_id = (data.get("room_id") or "").strip()
    owner_uid = (data.get("owner_uid") or "").strip()
    file_url = (data.get("file_url") or "").strip()

    if not room_id or not owner_uid or not file_url:
        raise HTTPException(status_code=400, detail="Missing room_id / owner_uid / file_url")

    if not _URL_RE.match(file_url):
        raise HTTPException(status_code=400, detail="file_url must be http(s) or /static/records/*.(webm|mp4)")

    if not owner_uid.isdigit():
        raise HTTPException(status_code=400, detail="owner_uid must be numeric")

    abs_url = _absolute_url(file_url)
    text = _build_message(room_id, abs_url)

    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    try:
        try:
            await bot.send_document(chat_id=int(owner_uid), document=abs_url, caption=text)
        except Exception:
            await bot.send_message(chat_id=int(owner_uid), text=text)
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass

    return {"ok": True}

