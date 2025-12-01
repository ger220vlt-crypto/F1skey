import sqlite3
import os
import telebot
from telebot import types
import datetime

# Настройки для Bothost
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'complaints.db')

# Подключаем базу данных
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицу с новым статусом
cursor.execute('''
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    first_name TEXT,
    complaint_text TEXT,
    status TEXT DEFAULT 'pending',  -- pending/approved/rejected
    admin_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()

# Токен и ID администратора
BOT_TOKEN = "8463911717:AAGXqlEqfUYHfGeV4ZeE2SYI3WlewsiKJpo"
ADMIN_ID = 7200109509  # ЗАМЕНИТЕ НА ВАШ ID

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

@bot.message_handler(commands=['start'])
def start(message):
    user_data[message.chat.id] = {'step': None}
    
    markup = types.InlineKeyboardMarkup()
    complaint_btn = types.InlineKeyboardButton("Оставить жалобу", callback_data="make_complaint")
    markup.add(complaint_btn)
    
    bot.send_message(message.chat.id, 
                    "Бот для приема жалоб студентов. Нажмите кнопку ниже чтобы оставить жалобу.", 
                    reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "make_complaint")
def start_complaint(call):
    user_data[call.message.chat.id] = {'step': 'waiting_complaint'}
    bot.edit_message_text("Напишите вашу жалобу или обращение:", 
                         call.message.chat.id, call.message.message_id)
    
    # Кнопка отмены
    cancel_markup = types.InlineKeyboardMarkup()
    cancel_btn = types.InlineKeyboardButton("Отмена", callback_data="cancel_complaint")
    cancel_markup.add(cancel_btn)
    bot.send_message(call.message.chat.id, "Нажмите 'Отмена' если передумали", reply_markup=cancel_markup)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_complaint")
def cancel_complaint(call):
    if call.message.chat.id in user_data:
        user_data[call.message.chat.id] = {'step': None}
    
    bot.edit_message_text("Подача жалобы отменена.", call.message.chat.id, call.message.message_id)
    start(call.message)

@bot.message_handler(func=lambda message: user_data.get(message.chat.id, {}).get('step') == 'waiting_complaint')
def process_complaint(message):
    complaint_text = message.text
    
    if len(complaint_text) < 10:
        bot.send_message(message.chat.id, "Слишком короткое сообщение. Опишите проблему подробнее (минимум 10 символов).")
        return
    
    if len(complaint_text) > 2000:
        bot.send_message(message.chat.id, "Слишком длинное сообщение. Сократите до 2000 символов.")
        return
    
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
        
        # Подтверждение пользователю
        confirm_text = f"""
✅ Ваша жалоба принята в обработку.

📄 Номер жалобы: #{complaint_id}
⏰ Время подачи: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

Ожидайте рассмотрения. Вы получите уведомление о результате.
        """
        
        # Кнопка для новой жалобы
        markup = types.InlineKeyboardMarkup()
        new_complaint_btn = types.InlineKeyboardButton("📝 Новая жалоба", callback_data="make_complaint")
        markup.add(new_complaint_btn)
        
        bot.send_message(message.chat.id, confirm_text, reply_markup=markup)
        
        # Отправляем жалобу администратору
        send_complaint_to_admin(complaint_id, message.from_user, complaint_text)
        
        # Сбрасываем состояние пользователя
        user_data[message.chat.id] = {'step': None}
        
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Произошла ошибка при сохранении жалобы. Попробуйте позже.")
        print(f"Database error: {e}")

def send_complaint_to_admin(complaint_id, user, complaint_text):
    """Отправляет жалобу администратору с кнопками Одобрено/Отказано"""
    admin_text = f"""
📨 НОВАЯ ЖАЛОБА #{complaint_id}

👤 От: {user.first_name or 'Неизвестно'} (@{user.username or 'нет username'})
🆔 ID пользователя: {user.id}
📅 Время подачи: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

📝 Текст жалобы:
{complaint_text}
"""
    
    # Кнопки для администратора
    markup = types.InlineKeyboardMarkup(row_width=2)
    approve_btn = types.InlineKeyboardButton("✅ Одобрено", callback_data=f"approve_{complaint_id}")
    reject_btn = types.InlineKeyboardButton("❌ Отказано", callback_data=f"reject_{complaint_id}")
    markup.add(approve_btn, reject_btn)
    
    try:
        bot.send_message(ADMIN_ID, admin_text, reply_markup=markup)
    except Exception as e:
        print(f"Error sending to admin: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def handle_admin_decision(call):
    """Обработка решения администратора"""
    parts = call.data.split('_')
    action = parts[0]  # 'approve' или 'reject'
    complaint_id = int(parts[1])
    
    # Запрашиваем комментарий администратора
    bot.send_message(ADMIN_ID, 
                    f"📝 Напишите комментарий для жалобы #{complaint_id} "
                    f"(или отправьте '-' если без комментария):")
    
    # Сохраняем ID жалобы для следующего сообщения
    bot.register_next_step_handler(call.message, 
                                  lambda msg: process_admin_comment(msg, complaint_id, action))

def process_admin_comment(message, complaint_id, action):
    """Обработка комментария администратора"""
    admin_comment = message.text
    
    # Получаем информацию о жалобе из базы
    cursor.execute("SELECT user_id, complaint_text FROM complaints WHERE id = ?", (complaint_id,))
    result = cursor.fetchone()
    
    if not result:
        bot.send_message(ADMIN_ID, "❌ Жалоба не найдена в базе данных.")
        return
    
    user_id, complaint_text = result
    
    # Обновляем статус в базе данных
    status = 'approved' if action == 'approve' else 'rejected'
    cursor.execute("UPDATE complaints SET status = ?, admin_comment = ? WHERE id = ?",
                  (status, admin_comment, complaint_id))
    conn.commit()
    
    # Отправляем уведомление пользователю
    send_decision_to_user(user_id, complaint_id, action, admin_comment, complaint_text)
    
    # Подтверждение администратору
    status_text = "✅ одобрена" if action == 'approve' else "❌ отклонена"
    bot.send_message(ADMIN_ID, f"Жалоба #{complaint_id} {status_text}. Пользователь уведомлен.")

def send_decision_to_user(user_id, complaint_id, action, admin_comment, complaint_text):
    """Отправляет решение администратора пользователю"""
    if action == 'approve':
        status_emoji = "✅"
        status_text = "ОДОБРЕНА"
        decision_text = "Ваша жалоба была рассмотрена и одобрена."
    else:
        status_emoji = "❌"
        status_text = "ОТКЛОНЕНА"
        decision_text = "К сожалению, ваша жалоба была отклонена."
    
    # Обрезаем длинную жалобу для уведомления
    complaint_preview = complaint_text[:200] + "..." if len(complaint_text) > 200 else complaint_text
    
    user_message = f"""
{status_emoji} РЕШЕНИЕ ПО ЖАЛОБЕ #{complaint_id}

{decision_text}

📄 Ваша жалоба:
\"{complaint_preview}\"

📝 Комментарий администратора:
{admin_comment if admin_comment != '-' else 'Без комментария'}

📅 Дата решения: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    
    try:
        bot.send_message(user_id, user_message)
    except Exception as e:
        print(f"Error sending to user {user_id}: {e}")
        # Если не удалось отправить (пользователь заблокировал бота), сообщаем администратору
        bot.send_message(ADMIN_ID, f"⚠️ Не удалось отправить уведомление пользователю {user_id}")

@bot.message_handler(commands=['stats'])
def stats(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к этой команде.")
        return
    
    # Статистика по статусам
    cursor.execute("SELECT COUNT(*) FROM complaints")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'pending'")
    pending = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'approved'")
    approved = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'rejected'")
    rejected = cursor.fetchone()[0]
    
    stats_text = f"""
📊 Статистика жалоб:

📨 Всего жалоб: {total}
⏳ Ожидают решения: {pending}
✅ Одобрено: {approved}
❌ Отклонено: {rejected}
"""
    bot.send_message(message.chat.id, stats_text)

@bot.message_handler(commands=['pending'])
def show_pending(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к этой команде.")
        return
    
    cursor.execute("SELECT id, first_name, complaint_text FROM complaints WHERE status = 'pending' ORDER BY created_at DESC")
    pending_complaints = cursor.fetchall()
    
    if not pending_complaints:
        bot.send_message(message.chat.id, "📭 Нет жалоб, ожидающих решения.")
        return
    
    text = "⏳ Жалобы, ожидающие решения:\n\n"
    for comp in pending_complaints:
        text += f"#{comp[0]} от {comp[1]}\n"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    if user_data.get(message.chat.id, {}).get('step') != 'waiting_complaint':
        bot.send_message(message.chat.id, 
                        "Используйте кнопку 'Оставить жалобу' для обращения или /start для главного меню.")

# Запуск бота
if __name__ == "__main__":
    print("🤖 Бот для жалоб студентов запущен")
    print(f"👮 Админ ID: {ADMIN_ID}")
    
    try:
        cursor.execute("SELECT 1")
        print("✅ База данных подключена")
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")
    
    bot.polling(none_stop=True)

