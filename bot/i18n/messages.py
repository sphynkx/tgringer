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
            "welcome": "Welcome! Use /newcall to start a video call."
        },
        "help": {
            "main": "Available commands:\n/start — Start the bot\n/newcall — Create a new invite\n/help — Show help"
        },
    },
############# RUSSIAN #################
    "ru": {
        "start": {
            "welcome": "Добро пожаловать! Используйте /newcall для создания видеозвонка."
        },
        "help": {
            "main": "Доступные команды:\n/start — Запустить бота\n/newcall — Создать новый инвайт\n/help — Показать справку"
        },
    },
}

