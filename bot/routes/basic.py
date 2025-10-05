from aiogram import Router, types, Bot, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.db.users import search_users
from bot.utils.invite import generate_room_id, build_invite_url
from bot.db.users import register_user
from bot.utils.userstate import get_user_state
from bot.i18n.messages import tr

router = Router()


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
    await message.answer(tr("start.welcome", lang=lang) )


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
    await message.answer(tr("newcall.msg", room_id=room_id, lang=state["lang"]), parse_mode="HTML")


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
        await message.answer(tr("mycall.current_room", room_id=room_id, lang=state["lang"]), parse_mode="HTML")
    else:
        await message.answer(tr("mycall.no_room", lang=state["lang"]))


@router.message(Command("find"))
async def cmd_find(message: types.Message):
    state = get_user_state(message.from_user.id)
    room_id = state.get("room_id")
    if not room_id:
        room_id = generate_room_id()
        state["room_id"] = room_id
        await message.answer(tr("find.new_room", room_id=room_id, lang=state["lang"]), parse_mode="HTML")

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
    webapp_url = f"https://tgringer.sphynkx.org.ua/app?room={room_id}"

    inviter_name = (
        inviter.full_name if inviter.full_name else inviter.username or str(inviter.id)
    )
    text = tr("invite.invited_by", inviter_name=inviter_name, lang=state["lang"]) + f"{tr('invite.name', lang=state['lang'])}: <b>{user_info['first_name']} {user_info['last_name'] or ''}</b>\n" + f"{tr('invite.username', lang=state['lang'])}: @{user_info['username'] or '-'}"

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
