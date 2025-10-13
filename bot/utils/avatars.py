import os
import urllib.request
from aiogram import Bot
from aiogram.types import PhotoSize
from bot.db.users import set_avatar_url


AVATARS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "server", "static", "avatars"))


def _ensure_dir():
    try:
        os.makedirs(AVATARS_DIR, exist_ok=True)
    except Exception:
        pass


async def ensure_user_avatar_cached(bot: Bot, user_id: int) -> str:
    """
    Fetch user's profile photo via Telegram API, cache it under server/static/avatars,
    and return a web-accessible URL path like /static/avatars/{user_id}.jpg.
    If user has no photos or fetching fails, returns empty string.
    """
    _ensure_dir()
    filename = f"{user_id}.jpg"
    full_path = os.path.join(AVATARS_DIR, filename)
    web_url = f"/static/avatars/{filename}"

    ## If already cached, reuse
    if os.path.exists(full_path):
        try:
            print(f"[BOT-AVATAR] reuse cached file for uid={user_id}: {web_url}")
        except Exception:
            pass
        return web_url

    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
        if not photos or not photos.total_count:
            print(f"[BOT-AVATAR] no photos for uid={user_id}")
            return ""
        sizes = photos.photos[0]  ## type: ignore
        if not sizes:
            print(f"[BOT-AVATAR] empty photo sizes for uid={user_id}")
            return ""

        ## Choose the largest size available
        best: PhotoSize = sizes[-1]

        ## Resolve file path via Telegram API
        file = await bot.get_file(best.file_id)
        if not getattr(file, "file_path", None):
            print(f"[BOT-AVATAR] no file_path for uid={user_id}")
            return ""

        ## Build direct download URL with bot token
        ## Safe in server-side context; we save locally and never expose this URL to clients.
        api_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"

        ## Download to disk
        tmp_path = full_path + ".part"
        print(f"[BOT-AVATAR] downloading uid={user_id} from {api_url}")
        with urllib.request.urlopen(api_url) as resp, open(tmp_path, "wb") as out:
            out.write(resp.read())
        os.replace(tmp_path, full_path)

        ## Persist URL in DB for later reuse (browser links, invites)
        await set_avatar_url(user_id, web_url)
        print(f"[BOT-AVATAR] cached uid={user_id} -> {web_url}")
        return web_url

    except Exception as e:
        try:
            print(f"[BOT-AVATAR] failed uid={user_id}: {e}")
        except Exception:
            pass
        return ""

