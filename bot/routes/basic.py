from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.db.users import register_user
from bot.utils.invite import generate_room_id, build_invite_url

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    await register_user(
        tg_user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        language_code=user.language_code or ""
    )
    await message.answer("Welcome! Use /newcall to create a call invite.")


@router.message(Command("newcall"))
async def cmd_newcall(message: types.Message):
    room_id = generate_room_id()
    url = build_invite_url(room_id)
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Open Web App",
        web_app=types.WebAppInfo(url=url)
    )
    kb.button(
        text="Open in browser",
        url=url
    )
    text = (
        f"Room created: <b>{room_id}</b>\n"
        f"Send the link to your contact or open Web App below.\n\n"
        f"<code>{url}</code>"
    )
    await message.answer(
        text,
        reply_markup=kb.as_markup()
    )

