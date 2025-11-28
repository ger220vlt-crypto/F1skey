import sqlite3
import os
import telebot
from telebot import types
import datetime

# Создаем папку для базы данных если её нет
os.makedirs('db', exist_ok=True)

# Подключаем базу данных
conn = sqlite3.connect('db/complaints.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицу для жалоб
cursor.execute('''
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    first_name TEXT,
    complaint_text TEXT,
    status TEXT DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()

# ЗАМЕНИТЕ НА ВАШ ТОКЕН БОТА
BOT_TOKEN = "8463911717:AAGXqlEqfUYHfGeV4ZeE2SYI3WlewsiKJpo"
# ЗАМЕНИТЕ НА ВАШ ID В TELEGRAM
ADMIN_ID = 7200109509  # Ваш ID

bot = telebot.TeleBot(BOT_TOKEN)

# Словарь для хранения временных данных
user_data = {}


@bot.message_handler(commands=['start'])
def start(message):
    user_data[message.chat.id] = {'step': None}

    markup = types.InlineKeyboardMarkup()
    complaint_btn = types.InlineKeyboardButton("Оставить жалобу", callback_data="make_complaint")
    markup.add(complaint_btn)

    welcome_text = "Бот для приема жалоб студентов. Нажмите кнопку ниже чтобы оставить жалобу."
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "make_complaint")
def start_complaint(call):
    user_data[call.message.chat.id] = {'step': 'waiting_complaint'}

    text = "Напишите вашу жалобу или обращение:"

    bot.edit_message_text(text, call.message.chat.id, call.message.message_id)

    # Отправляем кнопку отмены
    cancel_markup = types.InlineKeyboardMarkup()
    cancel_btn = types.InlineKeyboardButton("Отмена", callback_data="cancel_complaint")
    cancel_markup.add(cancel_btn)

    bot.send_message(call.message.chat.id, "Нажмите Отмена если передумали", reply_markup=cancel_markup)


@bot.callback_query_handler(func=lambda call: call.data == "cancel_complaint")
def cancel_complaint(call):
    if call.message.chat.id in user_data:
        user_data[call.message.chat.id] = {'step': None}

    bot.edit_message_text("Подача жалобы отменена.", call.message.chat.id, call.message.message_id)
    start(call.message)


@bot.message_handler(func=lambda message: user_data.get(message.chat.id, {}).get('step') == 'waiting_complaint')
def process_complaint(message):
    complaint_text = message.text

    # Проверяем длину жалобы
    if len(complaint_text) < 10:
        bot.send_message(message.chat.id,
                         "Слишком короткое сообщение. Опишите проблему подробнее (минимум 10 символов).")
        return

    if len(complaint_text) > 2000:
        bot.send_message(message.chat.id, "Слишком длинное сообщение. Сократите до 2000 символов.")
        return

    # Сохраняем жалобу в базу данных
    try:
        cursor.execute('''
        INSERT INTO complaints (user_id, username, first_name, complaint_text) 
        VALUES (?, ?, ?, ?)
        ''', (message.from_user.id,
              message.from_user.username,
              message.from_user.first_name,
              complaint_text))
        complaint_id = cursor.lastrowid
        conn.commit()

        # Отправляем подтверждение пользователю
        confirm_text = f"""
Ваша жалоба принята в обработку.

Номер жалобы: #{complaint_id}
Время подачи: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

Обращение будет рассмотрено в ближайшее время.
        """

        # Кнопка для новой жалобы
        markup = types.InlineKeyboardMarkup()
        new_complaint_btn = types.InlineKeyboardButton("Новая жалоба", callback_data="make_complaint")
        markup.add(new_complaint_btn)

        bot.send_message(message.chat.id, confirm_text, reply_markup=markup)

        # Отправляем жалобу администратору
        send_complaint_to_admin(complaint_id, message.from_user, complaint_text)

        # Сбрасываем состояние пользователя
        user_data[message.chat.id] = {'step': None}

    except Exception as e:
        bot.send_message(message.chat.id, "Произошла ошибка при сохранении жалобы. Попробуйте позже.")
        print(f"Database error: {e}")


def send_complaint_to_admin(complaint_id, user, complaint_text):
    """Отправляет жалобу администратору"""
    admin_text = f"""
НОВАЯ ЖАЛОБА #{complaint_id}

От: {user.first_name or 'Неизвестно'} (@{user.username or 'нет username'})
ID: {user.id}
Время: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

Текст жалобы:
{complaint_text}
"""

    # Кнопки для администратора
    markup = types.InlineKeyboardMarkup()
    replied_btn = types.InlineKeyboardButton("Отвечено", callback_data=f"replied_{complaint_id}")
    spam_btn = types.InlineKeyboardButton("Спам", callback_data=f"spam_{complaint_id}")
    markup.add(replied_btn, spam_btn)

    try:
        bot.send_message(ADMIN_ID, admin_text, reply_markup=markup)
    except Exception as e:
        print(f"Error sending to admin: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith(('replied_', 'spam_')))
def handle_admin_actions(call):
    """Обработка действий администратора"""
    complaint_id = int(call.data.split('_')[1])

    if call.data.startswith('replied_'):
        cursor.execute("UPDATE complaints SET status = 'replied' WHERE id = ?", (complaint_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "Жалоба помечена как отвеченная")
        bot.edit_message_text(f"Жалоба #{complaint_id} помечена как отвеченная",
                              call.message.chat.id, call.message.message_id)

    elif call.data.startswith('spam_'):
        cursor.execute("UPDATE complaints SET status = 'spam' WHERE id = ?", (complaint_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "Жалоба помечена как спам")
        bot.edit_message_text(f"Жалоба #{complaint_id} помечена как спам",
                              call.message.chat.id, call.message.message_id)


# Команда для администратора - статистика
@bot.message_handler(commands=['stats'])
def stats(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет доступа к этой команде.")
        return

    cursor.execute("SELECT COUNT(*) FROM complaints")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'new'")
    new = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'replied'")
    replied = cursor.fetchone()[0]

    stats_text = f"""
Статистика жалоб:

Всего жалоб: {total}
Новых: {new}
Отвеченных: {replied}
"""
    bot.send_message(message.chat.id, stats_text)


# Команда для администратора - просмотр жалоб
@bot.message_handler(commands=['complaints'])
def show_complaints(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет доступа к этой команде.")
        return

    cursor.execute("SELECT id, first_name, complaint_text, status FROM complaints ORDER BY id DESC LIMIT 10")
    complaints = cursor.fetchall()

    if not complaints:
        bot.send_message(message.chat.id, "Жалоб пока нет.")
        return

    text = "Последние 10 жалоб:\n\n"
    for comp in complaints:
        status_text = "НОВАЯ" if comp[3] == 'new' else "ОТВЕЧЕНО" if comp[3] == 'replied' else "СПАМ"
        text += f"#{comp[0]} от {comp[1]} - {status_text}\n"

    bot.send_message(message.chat.id, text)


# Обработка любых других сообщений
@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    if user_data.get(message.chat.id, {}).get('step') != 'waiting_complaint':
        bot.send_message(message.chat.id,
                         "Используйте кнопку 'Оставить жалобу' для обращения или /start для главного меню.")


if __name__ == "__main__":
    print("Бот для жалоб студентов запущен")
    print(f"Админ ID: {ADMIN_ID}")

    try:
        cursor.execute("SELECT 1")
        print("База данных подключена")
    except Exception as e:
        print(f"Ошибка базы данных: {e}")

    bot.polling(none_stop=True)