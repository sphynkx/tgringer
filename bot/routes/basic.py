from aiogram import Router, types, Bot, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.db.users import search_users
from bot.utils.invite import generate_room_id, build_invite_url
from bot.db.users import register_user
from bot.utils.userstate import get_user_state
from bot.i18n.messages import tr
from urllib.parse import quote

router = Router()


def _display_name(u: types.User) -> str:
    first_last = f"{u.first_name or ''} {u.last_name or ''}".strip()
    if first_last:
        return first_last
    if u.username:
        return f"@{u.username}"
    return str(u.id)


def _send_creator_links_kb(room_id: str, creator: types.User, lang: str) -> InlineKeyboardBuilder:
    creator_info = {
        "user_id": creator.id,
        "username": creator.username or "",
        "first_name": creator.first_name or "",
        "last_name": creator.last_name or "",
        "avatar_url": "",
        "lang": lang,
    }
    browser_url = build_invite_url(room_id, creator_info)
    # Pass human-readable name to WebApp via 'n' param to show local label even without USER_INFO
    name_param = quote(_display_name(creator))
    webapp_url = f"https://tgringer.sphynkx.org.ua/app?room={room_id}&n={name_param}"

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

    kb = _send_creator_links_kb(room_id, message.from_user, state["lang"])
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
        kb = _send_creator_links_kb(room_id, message.from_user, state["lang"])
        await message.answer(
            tr("mycall.current_room", room_id=room_id, lang=state["lang"]),
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    else:
        await message.answer(tr("mycall.no_room", lang=state["lang"]))


@router.message(Command("find"))
async def cmd_find(message: types.Message):
    state = get_user_state(message.from_user.id)
    room_id = state.get("room_id")
    if not room_id:
        # Full /newcall behavior first
        room_id = generate_room_id()
        state["room_id"] = room_id
        kb_room = _send_creator_links_kb(room_id, message.from_user, state["lang"])
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
        kb = InlineKeyboardBuilder()
        kb.button(
            text=tr("find.invite", lang=state["lang"]),
            callback_data=f"invite:{u['tg_user_id']}"
        )
        caption = (
            f"<b>{u['first_name']} {u['last_name'] or ''}</b>\n"
            f"@{u['username'] or '-'}\n"
            f"{tr('find.invite', lang=state['lang'])}: {u['status'] or '-'}"
        )
        if u["avatar_url"]:
            await message.answer_photo(
                photo=u["avatar_url"],
                caption=caption,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                caption,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )


@router.callback_query(F.data.startswith("invite:"))
async def invite_callback(call: types.CallbackQuery, bot: Bot):
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
        "avatar_url": u["avatar_url"],
        "lang": u["language_code"] or "en",
    }
    browser_url = build_invite_url(room_id, user_info)
    # WebApp: only room id; invitee will introduce name via WS hello or via USER_INFO if present
    webapp_url = f"https://tgringer.sphynkx.org.ua/app?room={room_id}"

    inviter_name = inviter.full_name if inviter.full_name else inviter.username or str(inviter.id)

    text_lines = [
        tr("invite.invited_by", inviter_name=inviter_name, lang=state["lang"]),
        f"{tr('invite.name', lang=state['lang'])}: <b>{user_info['first_name']} {user_info['last_name'] or ''}</b>",
        f"{tr('invite.username', lang=state['lang'])}: @{user_info['username'] or '-'}",
    ]
    text = "\n".join(text_lines)

    kb = InlineKeyboardBuilder()
    kb.button(text=tr("invite.browser_url", lang=state["lang"]), url=browser_url)
    kb.button(text=tr("invite.webapp_url", lang=state["lang"]), web_app=types.WebAppInfo(url=webapp_url))

    try:
        if u["avatar_url"]:
            await bot.send_photo(
                u["tg_user_id"],
                photo=u["avatar_url"],
                caption=text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                u["tg_user_id"],
                text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        await call.answer(tr("invite.sent", lang=state["lang"]), show_alert=True)
    except Exception as ex:
        await call.answer(f"{tr('invite.sent', lang=state['lang'])}: {ex}", show_alert=True)