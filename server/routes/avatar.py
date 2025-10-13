from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, AnyHttpUrl
import os
import urllib.request

router = APIRouter()

AVATARS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "avatars"))


class CacheAvatarRequest(BaseModel):
    uid: str
    url: AnyHttpUrl


class CacheAvatarResponse(BaseModel):
    avatar: str  ## web path like /static/avatars/<uid>.jpg


def _ensure_dir():
    try:
        os.makedirs(AVATARS_DIR, exist_ok=True)
    except Exception:
        pass


@router.post("/avatar/cache", response_model=CacheAvatarResponse)
async def cache_avatar(payload: CacheAvatarRequest):
    """
    Download avatar by URL and store as /static/avatars/<uid>.jpg, return web path.
    """
    _ensure_dir()
    uid = payload.uid.strip()
    if not uid:
        print("[AVATAR] bad request: empty uid")
        raise HTTPException(status_code=400, detail="uid is required")
    safe_uid = "".join(c for c in uid if c.isalnum() or c in ("-", "_"))
    if not safe_uid:
        print(f"[AVATAR] bad request: invalid uid={uid}")
        raise HTTPException(status_code=400, detail="invalid uid")
    filename = f"{safe_uid}.jpg"
    full_path = os.path.join(AVATARS_DIR, filename)
    try:
        tmp_path = full_path + ".part"
        print(f"[AVATAR] fetching uid={safe_uid} url={payload.url}")
        with urllib.request.urlopen(str(payload.url)) as resp, open(tmp_path, "wb") as out:
            out.write(resp.read())
        os.replace(tmp_path, full_path)
        web_path = f"/static/avatars/{filename}"
        print(f"[AVATAR] cached uid={safe_uid} -> {web_path}")
        return CacheAvatarResponse(avatar=web_path)
    except Exception as e:
        print(f"[AVATAR] fetch failed uid={safe_uid} err={e}")
        raise HTTPException(status_code=502, detail=f"failed to fetch avatar: {e}")

