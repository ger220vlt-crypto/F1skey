import sqlite3
import os
import telebot
from telebot import types
import datetime

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8463911717:AAGXqlEqfUYHfGeV4ZeE2SYI3WlewsiKJpo"  # Замените на токен от @BotFather
ADMIN_ID = 7200109509  # Замените на ваш ID

# ===== БАЗА ДАННЫХ =====
os.makedirs('db', exist_ok=True)
conn = sqlite3.connect('db/complaints.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    first_name TEXT,
    complaint_text TEXT,
    status TEXT DEFAULT 'pending',
    admin_id INTEGER,
    admin_username TEXT,
    decision_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()

# ===== ИНИЦИАЛИЗАЦИЯ БОТА =====
bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}

# ===== ОСНОВНЫЕ ФУНКЦИИ =====

@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработка команды /start"""
    user_states[message.chat.id] = {'state': None}
    
    markup = types.InlineKeyboardMarkup()
    new_complaint_btn = types.InlineKeyboardButton("📝 НАПИСАТЬ ЖАЛОБУ", callback_data="new_complaint")
    my_complaints_btn = types.InlineKeyboardButton("📋 МОИ ЖАЛОБЫ", callback_data="my_complaints")
    markup.add(new_complaint_btn)
    markup.add(my_complaints_btn)
    
    text = """
🔔 БОТ ДЛЯ ПРИЕМА ЖАЛОБ

Здесь вы можете оставить жалобу на любую проблему.
Ваши обращения будут рассмотрены администрацией.

👇 Выберите действие:
"""
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "new_complaint")
def start_new_complaint(call):
    """Начало написания новой жалобы"""
    user_states[call.message.chat.id] = {'state': 'waiting_complaint'}
    
    bot.edit_message_text(
        "📝 Напишите вашу жалобу:\n\n"
        "• Опишите проблему подробно\n"
        "• Укажите детали\n"
        "• Будьте конкретны\n\n"
        "📌 Минимум 20 символов.",
        call.message.chat.id,
        call.message.message_id
    )
    
    cancel_markup = types.InlineKeyboardMarkup()
    cancel_btn = types.InlineKeyboardButton("❌ ОТМЕНИТЬ", callback_data="cancel_complaint")
    cancel_markup.add(cancel_btn)
    
    bot.send_message(call.message.chat.id, "Нажмите ❌ ОТМЕНИТЬ если передумали", reply_markup=cancel_markup)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_complaint")
def cancel_complaint(call):
    """Отмена написания жалобы"""
    if call.message.chat.id in user_states:
        user_states[call.message.chat.id] = {'state': None}
    
    bot.edit_message_text(
        "❌ Написание жалобы отменено",
        call.message.chat.id,
        call.message.message_id
    )
    start_command(call.message)

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_complaint')
def save_complaint(message):
    """Сохранение жалобы в базу"""
    complaint_text = message.text.strip()
    
    if len(complaint_text) < 20:
        bot.send_message(message.chat.id, "❌ Слишком короткая жалоба. Минимум 20 символов.")
        return
    
    if len(complaint_text) > 2000:
        bot.send_message(message.chat.id, "❌ Слишком длинная жалоба. Максимум 2000 символов.")
        return
    
    try:
        cursor.execute('''
        INSERT INTO complaints (user_id, username, first_name, complaint_text)
        VALUES (?, ?, ?, ?)
        ''', (
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            complaint_text
        ))
        complaint_id = cursor.lastrowid
        conn.commit()
        
        user_markup = types.InlineKeyboardMarkup()
        new_complaint_btn = types.InlineKeyboardButton("📝 НОВАЯ ЖАЛОБА", callback_data="new_complaint")
        status_btn = types.InlineKeyboardButton("📊 СТАТУС ЖАЛОБ", callback_data="my_complaints")
        user_markup.add(new_complaint_btn, status_btn)
        
        confirm_text = f"""
✅ ЖАЛОБА ПРИНЯТА!

📄 Номер жалобы: #{complaint_id}
📅 Дата: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

🔄 Статус: ⏳ НА РАССМОТРЕНИИ

⏰ Ваша жалоба будет рассмотрена в течение 24 часов.
"""
        bot.send_message(message.chat.id, confirm_text, reply_markup=user_markup)
        
        send_to_admin(complaint_id, message.from_user, complaint_text)
        user_states[message.chat.id] = {'state': None}
        
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка при сохранении жалобы")
        print(f"Database error: {e}")

def send_to_admin(complaint_id, user, complaint_text):
    """Отправка жалобы администратору с кнопками"""
    admin_text = f"""
🚨 НОВАЯ ЖАЛОБА #{complaint_id}

👤 ОТ: {user.first_name or 'Не указано'}
📱 USERNAME: @{user.username or 'не указан'}
🆔 ID: {user.id}
📅 ДАТА: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

📝 ТЕКСТ ЖАЛОБЫ:
{complaint_text}
"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    approve_btn = types.InlineKeyboardButton("✅ ОДОБРИТЬ", callback_data=f"approve_{complaint_id}")
    reject_btn = types.InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_{complaint_id}")
    markup.add(approve_btn, reject_btn)
    
    try:
        bot.send_message(ADMIN_ID, admin_text, reply_markup=markup)
    except Exception as e:
        print(f"Error sending to admin: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def handle_decision(call):
    """Обработка решения администратора"""
    complaint_id = int(call.data.split('_')[1])
    action = 'approve' if call.data.startswith('approve_') else 'reject'
    
    cursor.execute('''
    UPDATE complaints 
    SET status = ?, 
        admin_id = ?, 
        admin_username = ?,
        decision_time = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (
        'approved' if action == 'approve' else 'rejected',
        call.from_user.id,
        call.from_user.username,
        complaint_id
    ))
    conn.commit()
    
    cursor.execute('SELECT user_id FROM complaints WHERE id = ?', (complaint_id,))
    result = cursor.fetchone()
    
    if result:
        user_id = result[0]
        
        if action == 'approve':
            decision_text = f"""
✅ ЖАЛОБА ОДОБРЕНА

📄 Номер жалобы: #{complaint_id}
📅 Дата решения: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

🎉 Ваша жалоба принята к рассмотрению и будет решена в ближайшее время.
"""
        else:
            decision_text = f"""
❌ ЖАЛОБА ОТКЛОНЕНА

📄 Номер жалобы: #{complaint_id}
📅 Дата решения: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

⚠️ Ваша жалоба не соответствует критериям или содержит недостоверную информацию.
"""
        
        try:
            bot.send_message(user_id, decision_text)
        except Exception as e:
            print(f"Error notifying user: {e}")
    
    status_text = "ОДОБРЕНА ✅" if action == 'approve' else "ОТКЛОНЕНА ❌"
    bot.edit_message_text(
        f"Жалоба #{complaint_id} {status_text}\n"
        f"👮 Администратор: @{call.from_user.username or 'не указан'}",
        call.message.chat.id,
        call.message.message_id
    )
    
    bot.answer_callback_query(call.id, f"✅ Решение принято: {status_text}")

@bot.callback_query_handler(func=lambda call: call.data == "my_complaints")
def show_my_complaints(call):
    """Показать жалобы пользователя"""
    cursor.execute('''
    SELECT id, complaint_text, status, created_at 
    FROM complaints 
    WHERE user_id = ? 
    ORDER BY id DESC 
    LIMIT 10
    ''', (call.from_user.id,))
    
    complaints = cursor.fetchall()
    
    if not complaints:
        text = "📭 У вас пока нет отправленных жалоб."
    else:
        text = "📋 ВАШИ ПОСЛЕДНИЕ ЖАЛОБЫ:\n\n"
        for comp in complaints:
            status_icon = "⏳" if comp[2] == 'pending' else "✅" if comp[2] == 'approved' else "❌"
            date_str = datetime.datetime.strptime(comp[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            text += f"{status_icon} #{comp[0]} - {date_str}\n"
    
    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")
    back_markup.add(back_btn)
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main(call):
    """Возврат в главное меню"""
    start_command(call.message)

# ===== КОМАНДЫ АДМИНИСТРАТОРА =====

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """Панель администратора"""
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой команде.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    stats_btn = types.InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats")
    pending_btn = types.InlineKeyboardButton("⏳ ОЖИДАЮЩИЕ", callback_data="admin_pending")
    all_complaints_btn = types.InlineKeyboardButton("📋 ВСЕ ЖАЛОБЫ", callback_data="admin_all")
    markup.add(stats_btn, pending_btn, all_complaints_btn)
    
    bot.send_message(message.chat.id, "👮 ПАНЕЛЬ АДМИНИСТРАТОРА", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    """Статистика жалоб"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    
    cursor.execute("SELECT COUNT(*) FROM complaints")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'pending'")
    pending = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'approved'")
    approved = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'rejected'")
    rejected = cursor.fetchone()[0]
    
    stats_text = f"""
📊 СТАТИСТИКА ЖАЛОБ:

📨 Всего жалоб: {total}
⏳ Ожидают решения: {pending}
✅ Одобрено: {approved}
❌ Отклонено: {rejected}
"""
    
    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin")
    back_markup.add(back_btn)
    
    bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_pending")
def admin_pending(call):
    """Жалобы ожидающие решения"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    
    cursor.execute('''
    SELECT id, first_name, complaint_text, created_at 
    FROM complaints 
    WHERE status = 'pending' 
    ORDER BY id DESC 
    LIMIT 20
    ''')
    
    pending = cursor.fetchall()
    
    if not pending:
        text = "📭 Нет жалоб ожидающих решения."
    else:
        text = "⏳ ЖАЛОБЫ ОЖИДАЮЩИЕ РЕШЕНИЯ:\n\n"
        for comp in pending:
            date_str = datetime.datetime.strptime(comp[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m %H:%M')
            text += f"#{comp[0]} - 👤 {comp[1]} - 🕐 {date_str}\n"
    
    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin")
    back_markup.add(back_btn)
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_all")
def admin_all(call):
    """Все жалобы"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    
    cursor.execute('''
    SELECT id, status, first_name, created_at 
    FROM complaints 
    ORDER BY id DESC 
    LIMIT 20
    ''')
    
    all_complaints = cursor.fetchall()
    
    text = "📋 ПОСЛЕДНИЕ 20 ЖАЛОБ:\n\n"
    for comp in all_complaints:
        status_icon = "⏳" if comp[1] == 'pending' else "✅" if comp[1] == 'approved' else "❌"
        date_str = datetime.datetime.strptime(comp[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m')
        text += f"{status_icon} #{comp[0]} - 👤 {comp[2]} - 📅 {date_str}\n"
    
    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin")
    back_markup.add(back_btn)
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_admin")
def back_to_admin(call):
    """Возврат в панель администратора"""
    if call.from_user.id == ADMIN_ID:
        admin_panel(call.message)

# ===== ЗАПУСК БОТА =====
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 БОТ ДЛЯ ПРИЕМА ЖАЛОБ ЗАПУЩЕН")
    print(f"👮 АДМИНИСТРАТОР: {ADMIN_ID}")
    print("=" * 50)
    
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
