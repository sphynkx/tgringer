## Chunked recording upload & finalization with selectable pipeline (A or B)
## A: collect .webm then single-pass mp4
## B: one ffmpeg process per session: FIFO input (streamed webm) -> segmented mp4; finish -> concat copy

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

RECORD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "records"))
os.makedirs(RECORD_DIR, exist_ok=True)

router = APIRouter()

## In-memory sessions (single-process MVP)
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

    ## Mode B requested: try to start ffmpeg FIFO segmenter. On failure fallback to A.
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

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        writer = open(fifo_path, "wb", buffering=0)

        session["session_dir"] = session_dir
        session["fifo_path"] = fifo_path
        session["fifo_writer"] = writer
        session["ffmpeg_proc"] = proc
        ACTIVE[recording_id] = session
        return {"ok": True, "recording_id": recording_id, "started_ts": started_ts}

    except Exception as e:
        ## Fallback to A
        try:
            if "ffmpeg_proc" in session and session.get("ffmpeg_proc"):
                try:
                    session["ffmpeg_proc"].terminate()
                except:
                    pass
            if os.path.isdir(session_dir):
                pass  ## dont remove; may contain partial files
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

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            mp4_path = os.path.join(RECORD_DIR, base + ".mp4")
            cmd = _ffmpeg_transcode_cmd_for_file(webm_path, mp4_path)
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                final_url = f"/static/records/{os.path.basename(mp4_path)}"
            except Exception as e:
                print(f"[RECORD] ffmpeg convert failed: {e} (keeping webm)")

        if send_to_bot:
            await _notify_bot(room_id, owner_uid, final_url)

        return {"ok": True, "url": final_url, "file": os.path.basename(final_url)}

    ## Mode B finalize
    writer = session.get("fifo_writer")
    proc: Optional[subprocess.Popen] = session.get("ffmpeg_proc")
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

    ## Cleanup session directory
    try:
        for f in os.listdir(session_dir):
            try:
                os.remove(os.path.join(session_dir, f))
            except:
                pass
        os.rmdir(session_dir)
    except Exception as e:
        print(f"[RECORD] cleanup warning: {e}")

    final_url = f"/static/records/{os.path.basename(final_mp4)}"

    if send_to_bot:
        await _notify_bot(room_id, owner_uid, final_url)

    return {"ok": True, "url": final_url, "file": os.path.basename(final_mp4)}


async def _notify_bot(room_id: str, owner_uid: str, url: str):
    bot_endpoint = os.environ.get("BOT_RECORD_NOTIFY_URL", "").strip()
    if not bot_endpoint:
        print("[RECORD] BOT_RECORD_NOTIFY_URL not set, skip notify")
        return
    payload = {"room_id": room_id, "owner_uid": owner_uid, "file_url": url}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(bot_endpoint, json=payload)
            if resp.status_code >= 300:
                print(f"[RECORD] bot notify failed status={resp.status_code} body={resp.text}")
            else:
                print("[RECORD] bot notified")
    except Exception as e:
        print(f"[RECORD] bot notify error: {e}")


@router.get("/record/list")
async def record_list():
    files = []
    for root, dirs, fnames in os.walk(RECORD_DIR):
        for fname in fnames:
            if fname.endswith(".webm") or fname.endswith(".mp4"):
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, RECORD_DIR)
                files.append({
                    "file": rel.replace("\\", "/"),
                    "url": f"/static/records/{rel.replace('\\', '/')}",
                    "size": os.path.getsize(path)
                })
    return {"records": sorted(files, key=lambda x: x["file"])}


@router.get("/record/file")
async def record_file(file: str):
    path = os.path.join(RECORD_DIR, file)
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="Not found")

