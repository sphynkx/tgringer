## Back-compat endpoint /bot/send_record with send mode switch 'link' or 'video'
## Env:
##   BOT_TOKEN
##   BOT_SEND_MODE = link | video
##   APP_BASE_URL (used to make absolute URLs when file_url is relative)

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Body

router = APIRouter()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BOT_SEND_MODE = (os.environ.get("BOT_SEND_MODE", "link") or "link").lower().strip()
APP_BASE_URL = (os.environ.get("APP_BASE_URL", "") or os.environ.get("PUBLIC_BASE_URL", "")).strip().rstrip("/")


async def _send_message(chat_id: str, text: str) -> Optional[dict]:
    if not BOT_TOKEN:
        print("[BOT] BOT_TOKEN not set")
        return None
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": False}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(api, json=payload)
        if r.status_code >= 300:
            print(f"[BOT] sendMessage failed status={r.status_code} body={r.text}")
            return None
        return r.json()


async def _send_video(chat_id: str, video_url: str, caption: str = "") -> Optional[dict]:
    if not BOT_TOKEN:
        print("[BOT] BOT_TOKEN not set")
        return None
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    data = {"chat_id": chat_id, "video": video_url, "supports_streaming": True, "caption": caption}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(api, data=data)
        if r.status_code >= 300:
            print(f"[BOT] sendVideo failed status={r.status_code} body={r.text}")
            return None
        return r.json()


def _absolute_url(u: str) -> str:
    if not u:
        return u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if APP_BASE_URL:
        return APP_BASE_URL + (u if u.startswith("/") else "/" + u)
    return u


@router.post("/bot/send_record")
async def send_record(payload: dict = Body(...)):
    """
    Expected payload:
      - file_url: required (mp4/webm). If relative, will be prefixed with APP_BASE_URL for Telegram fetch.
      - chat_id: optional; if absent and owner_uid present -> fallback chat_id = owner_uid
      - room_id, owner_uid: optional (for caption or fallback)
    """
    chat_id = str(payload.get("chat_id") or "").strip()
    file_url = (payload.get("file_url") or "").strip()
    room_id = (payload.get("room_id") or "").strip()
    owner_uid = (payload.get("owner_uid") or "").strip()

    if not file_url:
        return {"ok": False, "error": "missing file_url"}

    # Fallback: if no chat_id but we have owner_uid, use it as chat_id
    if not chat_id and owner_uid:
        chat_id = owner_uid

    # Make URL absolute for Telegram (sendVideo by URL requires Telegram to download it)
    file_url_abs = _absolute_url(file_url)

    caption = f"Room: {room_id}" if room_id else ""
    if owner_uid:
        caption = (caption + f" | Owner: {owner_uid}").strip(" |")

    ## No chat_id
    if not chat_id:
        print("[BOT] No chat_id and no owner_uid; cannot send to Telegram. Returning link-only result")
        return {"ok": True, "mode": "link", "url": file_url_abs}

    if BOT_SEND_MODE == "video":
        res = await _send_video(chat_id, file_url_abs, caption)
        return {"ok": bool(res), "mode": "video", "url": file_url_abs}

    text = (caption + "\n" if caption else "") + file_url_abs
    res = await _send_message(chat_id, text)
    return {"ok": bool(res), "mode": "link", "url": file_url_abs}
