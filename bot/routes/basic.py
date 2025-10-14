from urllib.parse import quote
from datetime import datetime, timezone

from aiogram import Router, types, Bot, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.users import search_users, register_user
from bot.utils.invite import generate_room_id, build_invite_url
from bot.utils.userstate import get_user_state
from bot.utils.avatars import ensure_user_avatar_cached
from bot.i18n.messages import tr
from bot.config import APP_BASE_URL

router = Router()


def _display_name(u: types.User) -> str:
    """Return best available display name for user."""
    first_last = f"{u.first_name or ''} {u.last_name or ''}".strip()
    if first_last:
        return first_last
    if u.username:
        return f"@{u.username}"
    return str(u.id)


def _humanize_status(last_seen: datetime | None, lang: str) -> str:
    """Human-readable online/last seen status via i18n messages."""
    if not last_seen:
        return "-"
    now = datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    sec = int((now - last_seen).total_seconds())
    if sec < 300:
        return tr("status.online", lang=lang)
    if sec < 3600:
        m = sec // 60
        return tr("status.last_seen_min", lang=lang, m=m)
    if sec < 86400:
        h = sec // 3600
        return tr("status.last_seen_hour", lang=lang, h=h)
    d = sec // 86400
    return tr("status.last_seen_day", lang=lang, d=d)


async def _send_creator_links_kb(message: types.Message, lang: str, room_id: str) -> InlineKeyboardBuilder:
    """Build inline keyboard with browser and webapp links for room creator.
    Important: provide avatar_url for the web client."""
    bot: Bot = message.bot  ## type: ignore

    ## Ensure Telegram avatar is cached as /static/avatars/<uid>.jpg
    avatar_url = await ensure_user_avatar_cached(bot, message.from_user.id)

    creator_info = {
        "user_id": message.from_user.id,
        "username": message.from_user.username or "",
        "first_name": message.from_user.first_name or "",
        "last_name": message.from_user.last_name or "",
        "avatar_url": avatar_url,  # relative path for web client
        "lang": lang,
    }

    ## Browser link: user_info + owner flag
    browser_url = build_invite_url(room_id, creator_info) + "&owner=1"

    ## WebApp link: include display name, uid and optionally avatar
    base_app = f"{APP_BASE_URL.rstrip('/')}/app"
    name_param = quote(_display_name(message.from_user))
    webapp_url = f"{base_app}?room={room_id}&n={name_param}&uid={message.from_user.id}&owner=1"
    if avatar_url:
        webapp_url += f"&a={quote(avatar_url)}"

    kb = InlineKeyboardBuilder()
    kb.button(text=tr("invite.browser_url", lang=lang), url=browser_url)
    kb.button(text=tr("invite.webapp_url", lang=lang), web_app=types.WebAppInfo(url=webapp_url))
    return kb


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    lang = get_user_state(message.from_user.id)["lang"]
    await register_user(
        tg_user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        language_code=user.language_code or ""
    )
    await message.answer(tr("start.welcome", lang=lang))


@router.message(Command("ru"))
async def swithch2ru(message: types.Message):
    state = get_user_state(message.from_user.id)
    state["lang"] = "ru"


@router.message(Command("en"))
async def swithch2en(message: types.Message):
    state = get_user_state(message.from_user.id)
    state["lang"] = "en"


@router.message(Command("help"))
async def helpmsg(message: types.Message):
    lang = get_user_state(message.from_user.id)["lang"]
    await message.answer(tr("help.msg", lang=lang))


@router.message(Command("newcall"))
async def newcall(message: types.Message):
    state = get_user_state(message.from_user.id)
    room_id = generate_room_id()
    state["room_id"] = room_id

    kb = await _send_creator_links_kb(message, state["lang"], room_id)
    await message.answer(
        tr("newcall.msg", room_id=room_id, lang=state["lang"]),
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@router.message(Command("endcall"))
async def endcall(message: types.Message):
    state = get_user_state(message.from_user.id)
    if "room_id" in state:
        del state["room_id"]
    await message.answer(tr("endcall.msg", lang=state["lang"]))


@router.message(Command("mycall"))
async def mycall(message: types.Message):
    state = get_user_state(message.from_user.id)
    room_id = state.get("room_id")
    if room_id:
        kb = await _send_creator_links_kb(message, state["lang"], room_id)
        await message.answer(
            tr("mycall.current_room", room_id=room_id, lang=state["lang"]),
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    else:
        await message.answer(tr("mycall.no_room", lang=state["lang"]))


@router.message(Command("find"))
async def cmd_find(message: types.Message):
    """Search users and show text-only cards (no images)."""
    state = get_user_state(message.from_user.id)
    room_id = state.get("room_id")
    if not room_id:
        room_id = generate_room_id()
        state["room_id"] = room_id
        kb_room = await _send_creator_links_kb(message, state["lang"], room_id)
        await message.answer(
            tr("newcall.msg", room_id=room_id, lang=state["lang"]),
            reply_markup=kb_room.as_markup(),
            parse_mode="HTML"
        )

    query = message.text.partition(' ')[2].strip()
    if not query:
        await message.answer(tr("find.usage", lang=state["lang"]))
        return

    users = await search_users(query)
    if not users:
        await message.answer(tr("find.no_members", lang=state["lang"]))
        return

    for u in users:
        ## Build inline keyboard
        kb = InlineKeyboardBuilder()
        kb.button(
            text=tr("find.invite", lang=state["lang"]),
            callback_data=f"invite:{u['tg_user_id']}"
        )

        ## Build caption
        lines = []
        full_name = f"{u['first_name'] or ''} {u['last_name'] or ''}".strip()
        title_name = full_name or (u.get('username') or str(u['tg_user_id']))
        lines.append(f"<b>{title_name}</b>")

        ## username only if present
        if u.get("username"):
            lines.append(f"@{u['username']}")

        ## status line
        status_text = _humanize_status(u.get("last_seen"), state["lang"])
        lines.append(f"{tr('find.status', lang=state['lang'])}: {status_text}")

        caption = "\n".join(lines)

        await message.answer(
            caption,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("invite:"))
async def invite_callback(call: types.CallbackQuery, bot: Bot):
    """
    Send invite links to the selected user (text only, no images).
    The bot can DM only those who started it and did not block it.
    """
    inviter = call.from_user
    state = get_user_state(inviter.id)
    room_id = state.get("room_id")
    if not room_id:
        await call.answer(tr("invite.no_room", lang=state["lang"]), show_alert=True)
        return

    target_user_id = int(call.data[len("invite:"):])
    users = await search_users(str(target_user_id))
    if not users:
        await call.answer(tr("invite.no_members", lang=state["lang"]), show_alert=True)
        return
    u = users[0]

    user_info = {
        "user_id": u["tg_user_id"],
        "username": u["username"],
        "first_name": u["first_name"],
        "last_name": u["last_name"],
        "avatar_url": u["avatar_url"] or "",  ## relative for web client if available
        "lang": u["language_code"] or "en",
    }

    browser_url = build_invite_url(room_id, user_info)

    base_app = f"{APP_BASE_URL.rstrip('/')}/app"
    invitee_display = f"{u['first_name'] or ''} {u['last_name'] or ''}".strip() or (f"@{u['username']}" if u["username"] else str(u["tg_user_id"]))
    webapp_url = f"{base_app}?room={room_id}&n={quote(invitee_display)}&uid={u['tg_user_id']}"

    inviter_name = inviter.full_name if inviter.full_name else inviter.username or str(inviter.id)

    text_lines = [
        tr("invite.invited_by", inviter_name=inviter_name, lang=state["lang"]),
        f"{tr('invite.name', lang=state['lang'])}: <b>{user_info['first_name']} {user_info['last_name'] or ''}</b>",
    ]
    if user_info["username"]:
        text_lines.append(f"{tr('invite.username', lang=state['lang'])}: @{user_info['username']}")
    text = "\n".join(text_lines)

    kb = InlineKeyboardBuilder()
    kb.button(text=tr("invite.browser_url", lang=state["lang"]), url=browser_url)
    kb.button(text=tr("invite.webapp_url", lang=state["lang"]), web_app=types.WebAppInfo(url=webapp_url))

    try:
        ## Send DM to the invitee (target user)
        await bot.send_message(
            u["tg_user_id"],
            text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        await call.answer(tr("invite.sent", lang=state["lang"]), show_alert=True)
    except Exception as ex:
        ## Common: user never pressed /start or blocked the bot
        await call.answer(f"{tr('invite.sent', lang=state['lang'])}: {ex}", show_alert=True)

