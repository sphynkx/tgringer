## Chunked recording upload & finalization with selectable pipeline (A or B)
## Adds call recording logging and events (best-effort, DB errors do not fail requests)

import os
import time
import shutil
import subprocess
from typing import Dict, Optional, Any, List

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from server.config import (
    RECORD_PIPELINE_MODE,
    RECORD_MP4_PRESET,
    RECORD_MP4_CRF,
    RECORD_MP4_A_BPS,
    RECORD_MP4_AR,
    RECORD_TARGET_WIDTH,
    RECORD_TARGET_HEIGHT,
    RECORD_TARGET_FPS,
    RECORD_TARGET_GOP,
    RECORD_SEGMENT_TIME,
)
from server.db import calls as callsdb
from server.db import get_pool

RECORD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "records"))
os.makedirs(RECORD_DIR, exist_ok=True)

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


def _ffmpeg_segment_cmd_for_fifo(fifo_path: str, out_pattern: str, segment_time: int) -> List[str]:
    return [
        "ffmpeg", "-y",
        "-fflags", "+genpts",
        "-i", fifo_path,
        "-c:v", "libx264",
        "-preset", RECORD_MP4_PRESET,
        "-crf", str(RECORD_MP4_CRF),
        "-pix_fmt", "yuv420p",
        "-r", str(RECORD_TARGET_FPS),
        "-s", f"{RECORD_TARGET_WIDTH}x{RECORD_TARGET_HEIGHT}",
        "-g", str(RECORD_TARGET_GOP),
        "-keyint_min", str(RECORD_TARGET_GOP),
        "-force_key_frames", f"expr:gte(t,n_forced*{segment_time})",
        "-c:a", "aac",
        "-b:a", RECORD_MP4_A_BPS,
        "-ar", str(RECORD_MP4_AR),
        "-ac", "2",
        "-movflags", "+faststart",
        "-f", "segment",
        "-segment_time", str(segment_time),
        "-reset_timestamps", "1",
        out_pattern,
    ]


@router.post("/record/start")
async def record_start(
    room_id: str = Form(...),
    owner_uid: str = Form(...),
):
    started_ts = str(int(time.time()))
    recording_id = f"{room_id}-{owner_uid}-{started_ts}"
    base = _build_base(room_id, owner_uid, started_ts)

    mode = (RECORD_PIPELINE_MODE or "A").upper()
    if mode not in ("A", "B"):
        mode = "A"

    session: Dict[str, Any] = {
        "mode": mode,
        "room_id": room_id,
        "owner_uid": owner_uid,
        "started_ts": started_ts,
        "base": base,
        "last_seq": 0,
    }

    try:
        call_id = await _resolve_call_id(room_id, owner_uid, int(started_ts))
        if call_id:
            await callsdb.add_event(call_id, None, "record_start", {"ts": started_ts})
        session["call_id"] = call_id
    except Exception as e:
        print(f"[RECORD] log record_start failed: {e}")

    if mode == "A":
        part_path = os.path.join(RECORD_DIR, base + ".webm.part")
        if os.path.exists(part_path):
            raise HTTPException(status_code=409, detail="Recording file already exists")
        try:
            fh = open(part_path, "ab")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cannot open file: {e}")
        session["part_path"] = part_path
        session["file_handle"] = fh
        ACTIVE[recording_id] = session
        return {"ok": True, "recording_id": recording_id, "started_ts": started_ts}

    session_dir = os.path.join(RECORD_DIR, base)
    try:
        os.makedirs(session_dir, exist_ok=True)
        fifo_path = os.path.join(session_dir, f"{base}.fifo")
        if os.path.exists(fifo_path):
            os.remove(fifo_path)
        os.mkfifo(fifo_path, mode=0o660)
        os.chmod(fifo_path, 0o660)

        out_pattern = os.path.join(session_dir, f"{base}_%06d.mp4")
        cmd = _ffmpeg_segment_cmd_for_fifo(fifo_path, out_pattern, max(1, int(RECORD_SEGMENT_TIME)))
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        writer = open(fifo_path, "wb", buffering=0)

        session["session_dir"] = session_dir
        session["fifo_path"] = fifo_path
        session["fifo_writer"] = writer
        session["ffmpeg_proc"] = proc

        ACTIVE[recording_id] = session
        return {"ok": True, "recording_id": recording_id, "started_ts": started_ts}

    except Exception as e:
        try:
            if "ffmpeg_proc" in session and session.get("ffmpeg_proc"):
                try:
                    session["ffmpeg_proc"].terminate()
                except:
                    pass
        except:
            pass

        part_path = os.path.join(RECORD_DIR, base + ".webm.part")
        try:
            fh = open(part_path, "ab")
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"Cannot fallback to A: {e2}")
        session["mode"] = "A"
        session.pop("session_dir", None)
        session.pop("fifo_path", None)
        session.pop("fifo_writer", None)
        session.pop("ffmpeg_proc", None)
        session["part_path"] = part_path
        session["file_handle"] = fh
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

    mode = session["mode"]

    if mode == "A":
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

    writer = session.get("fifo_writer")
    if not writer:
        raise HTTPException(status_code=500, detail="FIFO writer missing")

    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty chunk")
        writer.write(data)
        writer.flush()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FIFO write failed: {e}")

    session["last_seq"] = max(session.get("last_seq", 0), int(seq))
    return {"ok": True, "seq": int(seq)}


@router.post("/record/finish")
async def record_finish(
    recording_id: str = Form(...),
    send_to_bot: int = Form(1),
):
    session = ACTIVE.pop(recording_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Recording not found")

    mode = session["mode"]
    room_id = session["room_id"]
    owner_uid = session["owner_uid"]
    base = session["base"]
    started_ts = int(session["started_ts"])

    file_name_logged = None
    fmt_logged = "mp4"
    size_bytes_logged = None
    ended_ts = int(time.time())

    if mode == "A":
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
            await _notify_bot(room_id, owner_uid, final_url)

        try:
            await _log_recording(room_id, owner_uid, file_name_logged, started_ts, ended_ts, fmt_logged, size_bytes_logged, bool(send_to_bot), base)
        except Exception as e:
            print(f"[RECORD] _log_recording failed (ignored): {e}")

        return {"ok": True, "url": final_url, "file": os.path.basename(final_url)}

    writer = session.get("fifo_writer")
    proc = session.get("ffmpeg_proc")
    session_dir = os.path.join(RECORD_DIR, base)

    if writer:
        try:
            writer.flush()
            writer.close()
        except:
            pass

    if proc:
        try:
            proc.wait(timeout=60)
        except Exception:
            try:
                proc.terminate()
            except:
                pass

    if not os.path.isdir(session_dir):
        raise HTTPException(status_code=500, detail="Session dir missing")

    segs = [
        os.path.join(session_dir, f) for f in sorted(os.listdir(session_dir))
        if f.endswith(".mp4") and f.startswith(base + "_")
    ]
    if not segs:
        raise HTTPException(status_code=500, detail="No mp4 segments produced")

    list_path = os.path.join(session_dir, f"{base}_list.txt")
    with open(list_path, "w", encoding="utf-8") as lf:
        for p in segs:
            lf.write(f"file '{p}'\n")

    final_mp4_tmp = os.path.join(session_dir, f"{base}.mp4")
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        "-movflags", "+faststart",
        final_mp4_tmp
    ]
    try:
        subprocess.run(cmd_concat, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Concat failed: {e}")

    final_mp4 = os.path.join(RECORD_DIR, f"{base}.mp4")
    try:
        os.replace(final_mp4_tmp, final_mp4)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Move final failed: {e}")

    final_url = f"/static/records/{os.path.basename(final_mp4)}"
    file_name_logged = os.path.basename(final_mp4)
    fmt_logged = "mp4"
    size_bytes_logged = os.path.getsize(final_mp4)

    try:
        for f in os.listdir(session_dir):
            try:
                os.remove(os.path.join(session_dir, f))
            except:
                pass
        os.rmdir(session_dir)
    except Exception as e:
        print(f"[RECORD] cleanup warning: {e}")

    if send_to_bot:
        await _notify_bot(room_id, owner_uid, final_url)

    try:
        await _log_recording(room_id, owner_uid, file_name_logged, started_ts, ended_ts, fmt_logged, size_bytes_logged, bool(send_to_bot), base)
    except Exception as e:
        print(f"[RECORD] _log_recording failed (ignored): {e}")

    return {"ok": True, "url": final_url, "file": os.path.basename(final_mp4)}


async def _notify_bot(room_id: str, owner_uid: str, url: str):
    bot_endpoint = os.environ.get("BOT_RECORD_NOTIFY_URL", "").strip()
    if not bot_endpoint:
        print("[RECORD] BOT_RECORD_NOTIFY_URL not set, skip notify")
        return
    payload = {
        "room_id": room_id,
        "owner_uid": owner_uid,
        "chat_id": owner_uid,           # add explicit chat_id fallback
        "file_url": url
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
    """
    Find active call for (room_uid, owner), prefer not-ended; otherwise nearest started before recording.
    """
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
    """
    Append call_recordings row and update call_logs.recordings_json for the matching call.
    Best-effort: any DB errors are logged and ignored.
    """
    if not file_name:
        return
    try:
        call_id = await _resolve_call_id(room_uid, owner_tg_uid, started_ts)
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
