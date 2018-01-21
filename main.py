import telebot
import postgresql
import config
import re
from states import get_user_state, set_user_state

db = postgresql.open(config.dbconnect)
bot = telebot.TeleBot(config.token)

# текущие тренировки пользователей
trainings = {}


@bot.message_handler(func=lambda message: not get_user_state(message.from_user.id, db))
def start_messaging(message):
    user_id = message.from_user.id
    add_user(user_id)
    set_user_state(user_id, 'start', db)
    bot.send_message(message.chat.id,
                     "Здравствуйте! Наш бот может работать для вас в качестве вашего личного словаря, а также поможет запомнить трудно дающиеся вам слова.")
    bot.send_message(message.chat.id, 'Введите "/" и выбирите одну из предложенных команд: ')



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
    user_id = message.from_user.id
    set_user_state(user_id, "adding_word", db)
    bot.send_message(message.chat.id, 'Вводите карточки в формате word - перевод. /end - закончить: ')


# все слова, для тестов
@bot.message_handler(commands=["show_all_cards"])
def get_all_words(message):
    user_id = message.from_user.id
    words = db.prepare('select word_en, word_ru from word_translations where user_id = $1')
    reply = ''
    for i in words(user_id):
        reply += i[0] + ' - ' + i[1] + '\n'
    bot.send_message(message.chat.id, reply)
    set_user_state(user_id, 'start', db)


# ловим пользователя находящегося в состоянии удаления своей карточки
@bot.message_handler(func=lambda message: get_user_state(message.from_user.id, db) == 'word_deleting')
def delete_word(message):
    user_id = message.from_user.id
    word_count = db.prepare('select count(*) from word_translations where user_id = $1')
    word_count(user_id)
    str_count_before = re.findall(r'\d+', str(word_count))
    print(str_count_before)
    word_deleting = db.prepare('delete from word_translations where user_id = $1 and (word_en = $2 or word_ru = $2)')
    word_deleting(message.from_user.id, message.text)

    word_count(user_id)
    str_count_after = re.findall(r'\d+', str(word_count))
    print(str_count_after)

    set_user_state(user_id, 'start', db)


# помещаем пользователя в состояние удаления своей карточки
@bot.message_handler(commands=["delete_card"])
def delete_word_state(message):
    set_user_state(message.from_user.id, 'word_deleting', db)
    bot.send_message(message.chat.id, 'Введите либо слово либо перевод, которые хотите удалить: ')


# ловим конец операций
@bot.message_handler(commands=["end"])
def end_adding_words(message):
    set_user_state(message.from_user.id, 'start', db)


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
    try:
        word, translation = message.text.lower().split(" - ")
    except ValueError:
        bot.send_message(message.chat.id, "Введите карточку в правильном формате!")
    else:
        add_word(user_id, word, translation)
        bot.send_message(message.chat.id, 'Карточка успешно добавлена!')


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
def add_user(user_id):
    db_state = db.prepare("INSERT INTO user_states(user_id, state) VALUES ($1, $2)")
    db_state(user_id, "start")


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


@bot.message_handler(func=lambda message: get_user_state(message.from_user.id, db) == "start")
def help_show_main_message(message):
    bot.send_message(message.chat.id, 'Введите "/" и выбирите одну из предложенных команд: ')


def change_score(user_id, word, success=True):
    query_text = 'UPDATE word_translations SET score_en = score_en ' + (
        '+ 1' if success else '') + ', sum_en = sum_en + 1 ' \
                 + 'WHERE user_id = $1 AND word_en = $2'
    prepared_query = db.prepare(query_text)
    prepared_query(user_id, word)


if __name__ == '__main__':
    bot.polling(none_stop=True)
