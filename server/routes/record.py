## Chunked recording upload & finalization with optional MP4 conversion
## Notes:
## - Accepts chunk as UploadFile (no "Stream consumed" issues)
## - Finalizes .webm and optionally converts to MP4 (ultrafast + faststart)
## - Notifies bot with final link (webm or mp4)

import os
import time
import shutil
import subprocess
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

## Directory for recordings
RECORD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "records"))
os.makedirs(RECORD_DIR, exist_ok=True)

router = APIRouter()

## Active recordings registry (MVP: in-memory, single-process)
ACTIVE: Dict[str, Dict[str, Optional[str]]] = {}


def _safe_component(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in ("-", "_"))


def _build_base(room_id: str, owner_uid: str, started_ts: str) -> str:
    return f"{_safe_component(room_id)}_{_safe_component(owner_uid)}_{_safe_component(started_ts)}"


@router.post("/record/start")
async def record_start(
    room_id: str = Form(...),
    owner_uid: str = Form(...),
):
    ## Start session and open .part for append
    started_ts = str(int(time.time()))
    recording_id = f"{room_id}-{owner_uid}-{started_ts}"
    base = _build_base(room_id, owner_uid, started_ts)
    part_path = os.path.join(RECORD_DIR, base + ".webm.part")

    if os.path.exists(part_path):
        raise HTTPException(status_code=409, detail="Recording file already exists")

    try:
        fh = open(part_path, "ab")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot open file: {e}")

    ACTIVE[recording_id] = {
        "path": part_path,
        "room_id": room_id,
        "owner_uid": owner_uid,
        "started_ts": started_ts,
        "file_handle": fh,
    }
    return {"ok": True, "recording_id": recording_id, "started_ts": started_ts}


@router.post("/record/chunk")
async def record_chunk(
    recording_id: str = Form(...),
    seq: int = Form(...),
    file: UploadFile = File(...),  ## chunk content as UploadFile
):
    ## Append binary chunk
    rec = ACTIVE.get(recording_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No active recording")

    fh = rec.get("file_handle")
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

    return {"ok": True, "seq": seq}


@router.post("/record/finish")
async def record_finish(
    recording_id: str = Form(...),
    send_to_bot: int = Form(1),
):
    ## Finalize .part -> .webm, then optional ffmpeg -> .mp4, notify bot
    rec = ACTIVE.pop(recording_id, None)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    fh = rec.get("file_handle")
    part_path = rec.get("path")
    room_id = rec.get("room_id")
    owner_uid = rec.get("owner_uid")
    started_ts = rec.get("started_ts")

    if fh:
        try: fh.close()
        except: pass

    if not part_path or not os.path.exists(part_path):
        raise HTTPException(status_code=500, detail="Partial file missing")

    base = _build_base(room_id, owner_uid, started_ts)
    webm_path = os.path.join(RECORD_DIR, base + ".webm")
    try:
        os.replace(part_path, webm_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Finalize failed: {e}")

    final_url = f"/static/records/{os.path.basename(webm_path)}"

    ## Optional MP4 conversion for better preview (Telegram inline, many players)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        mp4_path = os.path.join(RECORD_DIR, base + ".mp4")
        try:
            ## Transcode to H.264 + AAC for compatibility and speed
            ## -preset ultrafast is fastest; adjust crf for quality-size
            subprocess.run(
                [
                    ffmpeg, "-y",
                    "-i", webm_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    mp4_path
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            final_url = f"/static/records/{os.path.basename(mp4_path)}"
        except Exception as e:
            print(f"[RECORD] ffmpeg convert failed: {e} (keeping webm)")

    if send_to_bot:
        await _notify_bot(room_id, owner_uid, final_url)

    return {"ok": True, "url": final_url, "file": os.path.basename(final_url)}


async def _notify_bot(room_id: str, owner_uid: str, url: str):
    """
    Notify bot to send link/file to owner.
    """
    bot_endpoint = os.environ.get("BOT_RECORD_NOTIFY_URL", "").strip()
    if not bot_endpoint:
        print("[RECORD] BOT_RECORD_NOTIFY_URL not set, skip notify")
        return
    payload = {
        "room_id": room_id,
        "owner_uid": owner_uid,
        "file_url": url,
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


@router.get("/record/list")
async def record_list():
    ## List existing recordings
    files = []
    for fname in os.listdir(RECORD_DIR):
        if fname.endswith(".webm") or fname.endswith(".mp4"):
            files.append({
                "file": fname,
                "url": f"/static/records/{fname}",
                "size": os.path.getsize(os.path.join(RECORD_DIR, fname))
            })
    return {"records": sorted(files, key=lambda x: x["file"])}


@router.get("/record/file")
async def record_file(file: str):
    ## Direct file download
    path = os.path.join(RECORD_DIR, file)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)

