import telebot
from telebot import types
import postgresql
import config
from states import get_user_state, set_user_state

db = postgresql.open(config.dbconnect)
bot = telebot.TeleBot(config.token)


# TODO убрать это
# слово-перевод, хрень
temp_words = {}

# текущие тренировки пользователей
trainings = {}


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

    #test
    bot.send_message(message.chat.id, 'Приветствую, выберите дальнейшее действие: ', reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    print(call)
    # Если сообщение из чата с ботом
    if call.message:
        if call.data == "test":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Пыщь")

# перевод пользователя в состояние добавления карточки
@bot.message_handler(commands=["add"])
def add_word_handler(message):
    print(message)
    user_id = message.from_user.id
    set_user_state(user_id, "adding_word", db)
    bot.send_message(message.chat.id, 'Введите слово на английском языке: ')


# все слова, для тестов
@bot.message_handler(commands=["get_words"])
def get_all_words(message):
    user_id = message.from_user.id
    words = get_words_for_training(user_id)
    reply = ''
    for i in words:
        reply += str(i) + '\n'
    bot.send_message(message.chat.id, reply)


# перевод пользователя в состояние добавления карточки
@bot.message_handler(commands=["training"])
def training_cmd_handler(message):
    user_id = message.from_user.id
    words = get_words_for_training(user_id)
    if len(words) > 0:
        set_user_state(user_id, "training", db)
        trainings[user_id] = words
        bot.send_message(message.chat.id, 'Введите перевод слова: ' + trainings[user_id][0][0])
    else:
        bot.send_message(message.chat.id, 'Список слов пуст. Сначала добавьте слова')


# обработка сообщений от пользователей, находящихся в состоянии добавления англ. слова
@bot.message_handler(func=lambda message: get_user_state(message.from_user.id, db) == "adding_word")
def adding_word(message):
    user_id = message.from_user.id
    temp_words[user_id] = message.text
    set_user_state(user_id, "adding_translation", db)
    bot.send_message(message.chat.id, 'Введите перевод слова ' + message.text)


# обработка сообщений от пользователей, находящихся в состоянии добавления перевода
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


# обработка сообщений от пользователей, находящихся в состоянии тренировки
@bot.message_handler(func=lambda message: get_user_state(message.from_user.id, db) == "training")
def user_training_handler(message):
    user_id = message.from_user.id
    card = trainings[user_id].pop(0)

    word, translation = card[0], card[1]
    user_answer = message.text.lower().strip()

    success = user_answer == translation
    change_score(user_id, word, success)

    reply = 'Верно!' if success else 'Неверно! Правильный ответ: ' + translation

    if len(trainings[user_id]) == 0:
        set_user_state(user_id, "start", db)
        reply += ' Тренировка окончена'
    else:
        reply += '\nВведите перевод слова: ' + trainings[user_id][0][0]

    bot.send_message(message.chat.id, reply)


# добавление пользователья в бд
def add_user(id):
    db_state = db.prepare("INSERT INTO user_states(user_id, state) VALUES ($1, $2)")
    db_state(id, "start")


# добавление карточки в бд
def add_word(user_id, word, translation):
    prep_statement = db.prepare("INSERT INTO word_translations(user_id, word_en, word_ru) VALUES ($1, $2, $3)")
    prep_statement(user_id, word, translation)


# функция выбора слов для тренировки
def get_words_for_training(user_id):
    db_words = db.prepare('\
        SELECT word_en "word", word_ru "translation", \
        CASE WHEN sum_en = 0 THEN 0 \
        	 ELSE score_en/sum_en \
             END "koef"\
        FROM word_translations\
        WHERE user_id = $1\
        ORDER BY "koef" DESC\
        LIMIT 5')
    return db_words(user_id)


def change_score(user_id, word, success = True):
    query_text = 'UPDATE word_translations SET score_en = score_en ' + ('+ 1' if success else '') + ', sum_en = sum_en + 1 ' \
               + 'WHERE user_id = $1 AND word_en = $2'
    prepared_query = db.prepare(query_text)
    prepared_query(user_id, word)

if __name__ == '__main__':
    bot.polling(none_stop=True)
