MESSAGES = {
    "en": {
        "ui": {
            "join": "Join call",
            "hangup": "Hang up",
            "copy": "Copy invite",
            "welcome": "Welcome to the video call!"
        }
    },
    "ru": {
        "ui": {
            "join": "Войти в звонок",
            "hangup": "Завершить",
            "copy": "Скопировать инвайт",
            "welcome": "Добро пожаловать в видеозвонок!"
        }
    }
}

def tr(key, lang="en"):
    ## key is string like "ui.join"
    d = MESSAGES.get(lang, MESSAGES["en"])
    for part in key.split("."):
        d = d.get(part, {})
    return d if isinstance(d, str) else "???"