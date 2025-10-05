user_state = {}


def get_user_state(user_id):
    default = {
        "lang": "en",
        "status": "offline"
    }
    if user_id not in user_state:
        user_state[user_id] = default.copy()
    return user_state[user_id]