from enum import Enum


class UserStates(Enum):
    START = "start"
    ADDING_WORD = "adding_word"
    ADDING_TRANSLATION = "adding_translation"
    TRAINING = "training"


def get_user_state(user_id, db):
    db_state = db.prepare("SELECT state FROM user_states  WHERE user_id = $1")
    state = db_state(user_id)
    print(state)
    if len(state) > 0:
        return state[0][0]
    else:
        return None


def set_user_state(user_id, state, db):
    db_state = db.prepare("UPDATE user_states SET state = $1 WHERE user_id = $2")
    state = db_state(state, user_id)
    return state