## User-state: user_id -> dict
## Store current method, direction, level and language for separate user.
user_state = {}


def get_user_state(user_id):
    default = {
        "lang": "en",         ## interface lang (initially from TG profile)
        "status": "offline",  ## online/offline/away
        "allow_add_me": True,
        "notifications": True
    }
    if user_id not in user_state:
        user_state[user_id] = default.copy()
    return user_state[user_id]

