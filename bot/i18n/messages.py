from bot.utils.userstate import get_user_state

def tr(key, user_id=None, lang="en", **kwargs):
    if user_id is not None:
        lang = get_user_state(user_id).get("lang", lang)
    d = MESSAGES.get(lang, MESSAGES["en"])
    for part in key.split('.'):
        d = d.get(part, {})
    if isinstance(d, str):
        return d.format(**kwargs)
    return "PUSTO"


MESSAGES = {
    "en": {
        "start": {
            "welcome": "Welcome! Use /newcall to create a call invite.\n Use /help for list of available commands.",
        },
        "help": {
            "msg": """
<b>List of available commands:</b>
/start - welcome message.
/help - this message.
/ru - switch to russian.
/en - switch to english.
/newcall - create new room for calling.
/endcall - remove active room.
/mycall - show active room ID or its absence.
/find - search members besides users who have run bot (by name or user ID).
            """,
        },
        "newcall": {
            "msg": "New room has been created: <code>{room_id}</code>",
        },
        "endcall": {
            "msg": "Current room has been removed.",
        },
        "mycall": {
            "current_room": "Current room: <code>{room_id}</code>",
            "no_room": "You haven't active room. Enter /newcall.",
        },
        "find": {
            "new_room": "Created new room: <code>{room_id}</code>",
            "usage": "Usage: /find (name or user ID)",
            "no_members": "Members not found.",
            "invite": "🤝 Invite",
            "status": "Status",
        },
        "invite": {
            "no_room": "You haven't active room. Enter /newcall.",
            "no_members": "Members not found.",
            "invited_by": "<b>{inviter_name}</b> invites you to video chat!!\n\n",
            "name": "Name",
            "username": "Username",
            "browser_url": "🌐 Open in browser",
            "webapp_url": "🤖 Open in Telegram WebApp",
            "sent": "Invite sent!!",
            "error": "Error",
        },
    },
############# RUSSIAN #################
    "ru": {
        "start": {
            "welcome": "Добро пожаловать! Используйте /newcall для создания видеозвонка. Для справки используйте /help .",
        },
        "help": {
            "msg": """
<b>Список доступных команд:</b>
/start - сообщение при запуске бота.
/help - данное сообщение.
/ru - переключиться на русский язык.
/en - переключиться на английский язык.
/newcall - создать новую комнату для созвона.
/endcall - удалить текущую комнату.
/mycall - показать ID текущей комнаты, либо сообщить о ее отсутствии.
/find - поиск участников среди пользователей бота (по имени или по ID телеграмм-аккаунта).
            """,
        },
        "newcall": {
            "msg": "Создана новая комната: <code>{room_id}</code>",
        },
        "endcall": {
            "msg": "Текущая комната сброшена.",
        },
        "mycall": {
            "current_room": "Текущая комната: <code>{room_id}</code>",
            "no_room": "У вас нет активной комнаты. Введите /newcall.",
        },
        "find": {
            "new_room": "Создана новая комната: <code>{room_id}</code>",
            "usage": "Использование: /find (имя или ИД)",
            "no_members": "Участники не найдены.",
            "invite": "🤝 Пригласить",
            "status": "Статус",
        },
        "invite": {
            "no_room": "У Вас нет активной комнаты. Введите /newcall.",
            "no_members": "Участники не найдены.",
            "invited_by": "Вас приглашает <b>{inviter_name}</b> в видео-чат!!\n\n",
            "name": "Имя",
            "username": "Юзернейм",
            "browser_url": "🌐 Открыть в броузере",
            "webapp_url": "🤖 Открыть в Telegram WebApp",
            "sent": "Приглашение отправлено!!",
            "error": "Ошибка",
        },
    },
}

