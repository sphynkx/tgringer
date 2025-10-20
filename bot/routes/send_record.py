## Back-compat endpoint /bot/send_record with send mode switch 'link' or 'video'
## Env:
##   BOT_TOKEN
##   BOT_SEND_MODE = link | video

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Body

router = APIRouter()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BOT_SEND_MODE = (os.environ.get("BOT_SEND_MODE", "link") or "link").lower().strip()


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


@router.post("/bot/send_record")
async def send_record(payload: dict = Body(...)):
    """
    Expected payload:
      - chat_id: optional if your bot resolves it by room_id/owner_uid internally
      - file_url: required (absolute https URL to mp4/webm)
      - room_id, owner_uid: optional, used for caption or routing
    """
    chat_id = str(payload.get("chat_id") or "").strip()
    file_url = (payload.get("file_url") or "").strip()
    room_id = (payload.get("room_id") or "").strip()
    owner_uid = (payload.get("owner_uid") or "").strip()

    if not file_url:
        return {"ok": False, "error": "missing file_url"}

    if not chat_id:
        print("[BOT] chat_id is empty; ensure your resolver is implemented or pass chat_id in payload")

    caption = f"Room: {room_id}" if room_id else ""
    if owner_uid:
        caption = (caption + f" | Owner: {owner_uid}").strip(" |")

    if os.environ.get("BOT_SEND_MODE", "link").lower().strip() == "video" and chat_id:
        res = await _send_video(chat_id, file_url, caption)
        return {"ok": bool(res), "mode": "video"}
    else:
        text = (caption + "\n" if caption else "") + file_url
        if chat_id:
            res = await _send_message(chat_id, text)
            return {"ok": bool(res), "mode": "link"}
        print("[BOT] No chat_id, cannot send to Telegram; returning link-only result")
        return {"ok": True, "mode": "link"}
