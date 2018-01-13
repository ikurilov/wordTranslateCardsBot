import telebot
from telebot import types
import postgresql
import config
from states import get_user_state, set_user_state

db = postgresql.open(config.dbconnect)
bot = telebot.TeleBot(config.token)

temp_words = {}


@bot.message_handler(commands=["start"])
def start_messaging(message):
    user_id = message.from_user.id
    if not get_user_state(message.from_user.id, db):
        add_user(user_id)
        print('user added')
    else:
        set_user_state(user_id, 'start', db)

    keyboard = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton(text="Добавить новое слово", callback_data="add_word")
    btn2 = types.InlineKeyboardButton(text="Начать тренировку", callback_data="start_training")
    keyboard.add(btn1)
    keyboard.add(btn2)

    bot.send_message(message.chat.id, 'Приветствую, выберите дальнейшее действие: ', reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    print(call)
    # Если сообщение из чата с ботом
    if call.message:
        if call.data == "test":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Пыщь")


@bot.message_handler(commands=["add"])
def add_word_handler(message):
    print("command add")
    user_id = message.from_user.id
    set_user_state(user_id, "adding_word", db)
    bot.send_message(message.chat.id, 'Введите слово на английском языке: ')


@bot.message_handler(commands=["get_words"])
def get_all_words(message):
    user_id = message.from_user.id
    words = get_words_for_training(user_id)
    reply = ''
    for i in words:
        reply += str(i) + '\n'
    bot.send_message(message.chat.id, reply)


@bot.message_handler(func=lambda message: get_user_state(message.from_user.id, db) == "adding_word")
def adding_word(message):
    user_id = message.from_user.id
    temp_words[user_id] = message.text
    set_user_state(user_id, "adding_translation", db)
    bot.send_message(message.chat.id, 'Введите перевод слова ' + message.text)


@bot.message_handler(func=lambda message: get_user_state(message.from_user.id, db) == "adding_translation")
def adding_translation(message):
    user_id = message.from_user.id
    word = temp_words[user_id]
    del temp_words[user_id]
    add_word(user_id, word, message.text)
    set_user_state(user_id, "start", db)

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    itembtn1 = types.KeyboardButton('/training')
    itembtn2 = types.KeyboardButton('/add')
    markup.add(itembtn1, itembtn2)

    bot.send_message(message.chat.id, 'Запись добавлена: ' + word + ':' + message.text, reply_markup=markup)


def add_user(id):
    db_state = db.prepare("INSERT INTO user_states(user_id, state) VALUES ($1, $2)")
    db_state(id, "start")


def add_word(user_id, word, translation):
    prep_statement = db.prepare("INSERT INTO word_translations(user_id, word_en, word_ru) VALUES ($1, $2, $3)")
    prep_statement(user_id, word, translation)


def get_words_for_training(user_id):
    db_words = db.prepare('SELECT *, CASE WHEN sum_en = 0 THEN 0 ELSE score_en/sum_en END "koef" \
                           FROM word_translations \
                           WHERE user_id = $1 \
                           ORDER BY "koef" DESC \
                           LIMIT 5')
    return db_words(user_id)


if __name__ == '__main__':
    bot.polling(none_stop=True)
