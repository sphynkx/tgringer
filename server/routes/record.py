## Recording routes (force Pipeline A for stability), best-effort DB log, browser chat_id/owner_uid support, absolute URL for bot notify

import os
import time
import shutil
import subprocess
from typing import Dict, Optional, Any, List

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from server.config import (
    RECORD_MP4_PRESET,
    RECORD_MP4_CRF,
    RECORD_MP4_A_BPS,
    RECORD_MP4_AR,
    RECORD_TARGET_WIDTH,
    RECORD_TARGET_HEIGHT,
    RECORD_TARGET_FPS,
    RECORD_TARGET_GOP,
)
from server.db import calls as callsdb
from server.db import get_pool

RECORD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "records"))
os.makedirs(RECORD_DIR, exist_ok=True)

APP_BASE_URL = (os.environ.get("APP_BASE_URL", "") or os.environ.get("PUBLIC_BASE_URL", "")).strip().rstrip("/")

router = APIRouter()

ACTIVE: Dict[str, Dict[str, Any]] = {}


def _safe_component(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in ("-", "_"))


def _build_base(room_id: str, owner_uid: str, started_ts: str) -> str:
    return f"{_safe_component(room_id)}_{_safe_component(owner_uid)}_{_safe_component(started_ts)}"


def _ffmpeg_transcode_cmd_for_file(input_path: str, output_path: str) -> List[str]:
    return [
        "ffmpeg", "-y",
        "-fflags", "+genpts",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", RECORD_MP4_PRESET,
        "-crf", str(RECORD_MP4_CRF),
        "-pix_fmt", "yuv420p",
        "-r", str(RECORD_TARGET_FPS),
        "-s", f"{RECORD_TARGET_WIDTH}x{RECORD_TARGET_HEIGHT}",
        "-g", str(RECORD_TARGET_GOP),
        "-keyint_min", str(RECORD_TARGET_GOP),
        "-c:a", "aac",
        "-b:a", RECORD_MP4_A_BPS,
        "-ar", str(RECORD_MP4_AR),
        "-ac", "2",
        "-movflags", "+faststart",
        output_path,
    ]


def _absolute_url(u: str) -> str:
    if not u:
        return u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if APP_BASE_URL:
        return APP_BASE_URL + (u if u.startswith("/") else "/" + u)
    return u


async def _fallback_owner_uid(room_uid: str) -> Optional[str]:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT u.tg_user_id "
                    "FROM call_logs cl JOIN users u ON u.id = cl.owner_id "
                    "WHERE cl.room_uid=%s AND cl.ended_at IS NULL "
                    "ORDER BY cl.started_at DESC LIMIT 1",
                    (room_uid,)
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return str(row[0])
                await cur.execute(
                    "SELECT u.tg_user_id "
                    "FROM call_logs cl JOIN users u ON u.id = cl.owner_id "
                    "WHERE cl.room_uid=%s "
                    "ORDER BY cl.started_at DESC LIMIT 1",
                    (room_uid,)
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return str(row[0])
    except Exception as e:
        print(f"[RECORD] owner fallback failed (ignored): {e}")
    return None


@router.post("/record/start")
async def record_start(
    room_id: str = Form(...),
    owner_uid: str = Form(""),
    chat_id: str = Form(""),
):
    started_ts = str(int(time.time()))
    if not owner_uid:
        try:
            got = await _fallback_owner_uid(room_id)
            if got:
                owner_uid = got
        except Exception as e:
            print(f"[RECORD] owner_uid fallback at start failed: {e}")

    owner_uid_for_base = owner_uid or "unknown"
    recording_id = f"{room_id}-{owner_uid_for_base}-{started_ts}"
    base = _build_base(room_id, owner_uid_for_base, started_ts)

    # Force Pipeline A for stability (single webm + optional mp4)
    session: Dict[str, Any] = {
        "mode": "A",
        "room_id": room_id,
        "owner_uid": owner_uid,
        "chat_id": (chat_id or owner_uid or ""),
        "started_ts": started_ts,
        "base": base,
        "last_seq": 0,
    }

    print(f"[RECORD] start room={room_id} owner_uid={owner_uid} chat_id={session['chat_id']} mode=A")

    part_path = os.path.join(RECORD_DIR, base + ".webm.part")
    if os.path.exists(part_path):
        raise HTTPException(status_code=409, detail="Recording file already exists")
    try:
        fh = open(part_path, "ab")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot open file: {e}")
    session["part_path"] = part_path
    session["file_handle"] = fh

    try:
        call_id = await _resolve_call_id(room_id, owner_uid, int(started_ts)) if owner_uid else None
        if call_id:
            await callsdb.add_event(call_id, None, "record_start", {"ts": started_ts})
        session["call_id"] = call_id
    except Exception as e:
        print(f"[RECORD] log record_start failed: {e}")

    ACTIVE[recording_id] = session
    return {"ok": True, "recording_id": recording_id, "started_ts": started_ts}


@router.post("/record/chunk")
async def record_chunk(
    recording_id: str = Form(...),
    seq: int = Form(...),
    file: UploadFile = File(...),
):
    session = ACTIVE.get(recording_id)
    if not session:
        raise HTTPException(status_code=404, detail="No active recording")

    fh = session.get("file_handle")
    if not fh:
        raise HTTPException(status_code=500, detail="File handle missing")
    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty chunk")
        fh.write(data)
        fh.flush()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write failed: {e}")
    session["last_seq"] = max(session.get("last_seq", 0), int(seq))
    return {"ok": True, "seq": int(seq)}


@router.post("/record/finish")
async def record_finish(
    recording_id: str = Form(...),
    send_to_bot: int = Form(1),
    owner_uid: str = Form(""),
    chat_id: str = Form(""),
):
    session = ACTIVE.pop(recording_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Recording not found")

    room_id = session["room_id"]

    owner_uid_eff = (owner_uid or "").strip() or (session.get("owner_uid") or "").strip()
    if not owner_uid_eff:
        try:
            got = await _fallback_owner_uid(room_id)
            if got:
                owner_uid_eff = got
        except Exception as e:
            print(f"[RECORD] owner_uid fallback at finish failed: {e}")

    chat_id_eff = (chat_id or "").strip() or (session.get("chat_id") or "").strip() or owner_uid_eff

    base = session["base"]
    started_ts = int(session["started_ts"])

    file_name_logged = None
    fmt_logged = "mp4"
    size_bytes_logged = None
    ended_ts = int(time.time())

    print(f"[RECORD] finish room={room_id} owner_uid={owner_uid_eff} chat_id={chat_id_eff} mode=A")

    fh = session.get("file_handle")
    if fh:
        try:
            fh.close()
        except:
            pass
    part_path = session.get("part_path")
    if not part_path or not os.path.exists(part_path):
        raise HTTPException(status_code=500, detail="Partial file missing")
    webm_path = os.path.join(RECORD_DIR, base + ".webm")
    try:
        os.replace(part_path, webm_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Finalize failed: {e}")

    final_url = f"/static/records/{os.path.basename(webm_path)}"
    file_name_logged = os.path.basename(webm_path)
    fmt_logged = "webm"
    size_bytes_logged = os.path.getsize(webm_path)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        mp4_path = os.path.join(RECORD_DIR, base + ".mp4")
        cmd = _ffmpeg_transcode_cmd_for_file(webm_path, mp4_path)
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            final_url = f"/static/records/{os.path.basename(mp4_path)}"
            file_name_logged = os.path.basename(mp4_path)
            fmt_logged = "mp4"
            size_bytes_logged = os.path.getsize(mp4_path)
        except Exception as e:
            print(f"[RECORD] ffmpeg convert failed: {e} (keeping webm)")

    if send_to_bot:
        await _notify_bot(room_id, owner_uid_eff, chat_id_eff, final_url)

    try:
        await _log_recording(room_id, owner_uid_eff, file_name_logged, started_ts, ended_ts, fmt_logged, size_bytes_logged, bool(send_to_bot), base)
    except Exception as e:
        print(f"[RECORD] _log_recording failed (ignored): {e}")

    return {"ok": True, "url": final_url, "file": os.path.basename(final_url)}


async def _notify_bot(room_id: str, owner_uid: str, chat_id: str, url: str):
    bot_endpoint = os.environ.get("BOT_RECORD_NOTIFY_URL", "").strip()
    if not bot_endpoint:
        print("[RECORD] BOT_RECORD_NOTIFY_URL not set, skip notify")
        return
    payload = {
        "room_id": room_id,
        "owner_uid": owner_uid or "",
        "chat_id": (chat_id or owner_uid or ""),
        "file_url": _absolute_url(url)
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(bot_endpoint, json=payload)
            if resp.status_code >= 300:
                print(f"[RECORD] bot notify failed status={resp.status_code} body={resp.text}")
            else:
                print("[RECORD] bot notified")
    except Exception as e:
        print(f"[RECORD] bot notify error: {e}")


async def _resolve_call_id(room_uid: str, owner_tg_uid: str, rec_started_ts: int) -> Optional[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            owner_id = await callsdb.get_user_id_by_tg(owner_tg_uid)
            if not owner_id:
                return None
            await cur.execute(
                "SELECT id FROM call_logs WHERE room_uid=%s AND owner_id=%s AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (room_uid, owner_id)
            )
            row = await cur.fetchone()
            if row:
                return int(row[0])
            await cur.execute(
                "SELECT id FROM call_logs WHERE room_uid=%s AND owner_id=%s AND started_at<=FROM_UNIXTIME(%s) ORDER BY started_at DESC LIMIT 1",
                (room_uid, owner_id, rec_started_ts)
            )
            row = await cur.fetchone()
            return int(row[0]) if row else None


async def _log_recording(room_uid: str, owner_tg_uid: str, file_name: Optional[str], started_ts: int, ended_ts: int, fmt: str, size_bytes: Optional[int], sent_to_bot: bool, base_name: Optional[str]) -> None:
    if not file_name:
        return
    try:
        call_id = await _resolve_call_id(room_uid, owner_tg_uid, started_ts) if owner_tg_uid else None
    except Exception as e:
        print(f"[RECORD] resolve call id failed (ignored): {e}")
        return
    if not call_id:
        return
    dur = max(0, int(ended_ts - started_ts))
    try:
        await callsdb.add_recording(call_id, file_name, started_ts, ended_ts, dur, fmt, size_bytes, sent_to_bot, base_name)
    except Exception as e:
        print(f"[RECORD] add_recording failed (ignored): {e}")