import sqlite3
import os
import telebot
from telebot import types
import datetime

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8463911717:AAGXqlEqfUYHfGeV4ZeE2SYI3WlewsiKJpo"  # Замените на токен от @BotFather

# ===== СПИСОК АДМИНИСТРАТОРОВ =====
ADMIN_IDS = [
    7200109509,
    1232171882,    # ID первого админа
    523416060,    # ID второго админа
]

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
    admin_comment TEXT DEFAULT '',
    decision_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()

# ===== ИНИЦИАЛИЗАЦИЯ БОТА =====
bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}

# ===== ФУНКЦИИ =====

def is_admin(user_id):
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

def send_to_all_admins(text, markup=None):
    """Отправляет сообщение всем администраторам"""
    for admin_id in ADMIN_IDS:
        try:
            if markup:
                bot.send_message(admin_id, text, reply_markup=markup)
            else:
                bot.send_message(admin_id, text)
        except Exception as e:
            print(f"⚠️ Не удалось отправить сообщение админу {admin_id}: {e}")

# ===== ОСНОВНЫЕ ФУНКЦИИ =====

@bot.message_handler(commands=['start'])
def start_command(message):
    user_states[message.chat.id] = {'state': None}
    
    markup = types.InlineKeyboardMarkup()
    new_complaint_btn = types.InlineKeyboardButton("📝 НАПИСАТЬ ЖАЛОБУ", callback_data="new_complaint")
    my_complaints_btn = types.InlineKeyboardButton("📋 МОИ ЖАЛОБЫ", callback_data="my_complaints")
    markup.add(new_complaint_btn)
    markup.add(my_complaints_btn)
    
    if is_admin(message.from_user.id):
        admin_btn = types.InlineKeyboardButton("👮 АДМИН ПАНЕЛЬ", callback_data="admin_panel")
        markup.add(admin_btn)
    
    text = """
🔔 БОТ ДЛЯ ПРИЕМА ЖАЛОБ

Здесь вы можете оставить жалобу на любую проблему.
Ваши обращения будут рассмотрены администрацией.

👇 Выберите действие:
"""
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "new_complaint")
def start_new_complaint(call):
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
    if call.message.chat.id in user_states:
        user_states[call.message.chat.id] = {'state': None}
    
    bot.edit_message_text("❌ Написание жалобы отменено", call.message.chat.id, call.message.message_id)
    start_command(call.message)

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_complaint')
def save_complaint(message):
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
        
        send_complaint_to_admin(complaint_id, message.from_user, complaint_text)
        user_states[message.chat.id] = {'state': None}
        
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка при сохранении жалобы")
        print(f"Database error: {e}")

def send_complaint_to_admin(complaint_id, user, complaint_text):
    """Отправляет жалобу администраторам - сообщение НЕ изменяется после решения"""
    admin_text = f"""
🚨 НОВАЯ ЖАЛОБА #{complaint_id}

👤 ОТ: {user.first_name or 'Не указано'}
📱 USERNAME: @{user.username or 'не указан'}
🆔 ID: {user.id}
📅 ДАТА: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

📝 ТЕКСТ ЖАЛОБЫ:
{complaint_text}

⚡ Статус: ⏳ ОЖИДАЕТ РЕШЕНИЯ
"""
    
    # Кнопки для администратора
    markup = types.InlineKeyboardMarkup(row_width=2)
    approve_btn = types.InlineKeyboardButton("✅ ОДОБРИТЬ", callback_data=f"approve_{complaint_id}")
    reject_btn = types.InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_{complaint_id}")
    markup.add(approve_btn, reject_btn)
    
    # Отправляем всем администраторам
    send_to_all_admins(admin_text, markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def handle_admin_decision(call):
    """Обработка решения администратора"""
    complaint_id = int(call.data.split('_')[1])
    action = 'approve' if call.data.startswith('approve_') else 'reject'
    
    # Получаем информацию о жалобе до обновления
    cursor.execute('''
    SELECT user_id, username, first_name, complaint_text, created_at 
    FROM complaints WHERE id = ?
    ''', (complaint_id,))
    complaint = cursor.fetchone()
    
    if not complaint:
        bot.answer_callback_query(call.id, "❌ Жалоба не найдена")
        return
    
    user_id, username, first_name, complaint_text, created_at = complaint
    
    # Обновляем статус в базе
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
        call.from_user.username or call.from_user.first_name,
        complaint_id
    ))
    conn.commit()
    
    # Уведомляем пользователя
    if action == 'approve':
        decision_text = f"""
✅ ЖАЛОБА ОДОБРЕНА

📄 Номер жалобы: #{complaint_id}
📅 Дата решения: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}
👮 Администратор: @{call.from_user.username or call.from_user.first_name}

🎉 Ваша жалоба принята к рассмотрению и будет решена в ближайшее время.

📝 Ваш текст жалобы:
{complaint_text[:500]}
"""
    else:
        decision_text = f"""
❌ ЖАЛОБА ОТКЛОНЕНА

📄 Номер жалобы: #{complaint_id}
📅 Дата решения: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}
👮 Администратор: @{call.from_user.username or call.from_user.first_name}

⚠️ Ваша жалоба не соответствует критериям или содержит недостоверную информацию.

📝 Ваш текст жалобы:
{complaint_text[:500]}
"""
    
    try:
        bot.send_message(user_id, decision_text)
    except Exception as e:
        print(f"Error notifying user: {e}")
    
    # Обновляем сообщение у администратора (но не удаляем его!)
    status_text = "ОДОБРЕНА ✅" if action == 'approve' else "ОТКЛОНЕНА ❌"
    decision_date = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    
    updated_text = f"""
📋 ЖАЛОБА #{complaint_id} - {status_text}

👤 От: {first_name} (@{username or 'нет'})
📅 Дата подачи: {datetime.datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')}
📅 Дата решения: {decision_date}
👮 Решил: @{call.from_user.username or call.from_user.first_name}

📝 Текст жалобы:
{complaint_text}

✅ Решение принято: {status_text}
"""
    
    # Создаем кнопки для просмотра решения
    markup = types.InlineKeyboardMarkup()
    view_decision_btn = types.InlineKeyboardButton("👁️‍🗨️ ПРОСМОТР РЕШЕНИЯ", callback_data=f"view_decision_{complaint_id}")
    markup.add(view_decision_btn)
    
    bot.edit_message_text(
        updated_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    
    bot.answer_callback_query(call.id, f"✅ Решение принято: {status_text}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_decision_'))
def view_decision(call):
    """Просмотр решения по жалобе"""
    complaint_id = int(call.data.split('_')[2])
    
    cursor.execute('''
    SELECT c.*, a.username as admin_username
    FROM complaints c
    LEFT JOIN complaints a ON c.admin_id = a.id
    WHERE c.id = ?
    ''', (complaint_id,))
    
    complaint = cursor.fetchone()
    
    if complaint:
        # Формируем полную информацию о жалобе
        status_icon = "⏳" if complaint[5] == 'pending' else "✅" if complaint[5] == 'approved' else "❌"
        status_text = "ОЖИДАЕТ" if complaint[5] == 'pending' else "ОДОБРЕНА" if complaint[5] == 'approved' else "ОТКЛОНЕНА"
        
        info_text = f"""
📋 ПОЛНАЯ ИНФОРМАЦИЯ О ЖАЛОБЕ #{complaint_id}

{status_icon} Статус: {status_text}

👤 Отправитель: {complaint[3]}
📱 Username: @{complaint[2] or 'не указан'}
🆔 User ID: {complaint[1]}

📅 Дата подачи: {datetime.datetime.strptime(complaint[9], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')}
"""
        
        if complaint[5] != 'pending':
            info_text += f"""
👮 Решил: @{complaint[7] or complaint[6]}
📅 Дата решения: {datetime.datetime.strptime(complaint[8], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')}
"""
        
        info_text += f"""
📝 Текст жалобы:
{complaint[4]}
"""
        
        markup = types.InlineKeyboardMarkup()
        back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin")
        markup.add(back_btn)
        
        bot.edit_message_text(info_text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "my_complaints")
def show_my_complaints(call):
    """Показать жалобы пользователя - все жалобы, даже обработанные"""
    cursor.execute('''
    SELECT id, complaint_text, status, created_at, decision_time, admin_username
    FROM complaints 
    WHERE user_id = ? 
    ORDER BY id DESC 
    LIMIT 15
    ''', (call.from_user.id,))
    
    complaints = cursor.fetchall()
    
    if not complaints:
        text = "📭 У вас пока нет отправленных жалоб."
    else:
        text = "📋 ВАШИ ЖАЛОБЫ:\n\n"
        for comp in complaints:
            status_icon = "⏳" if comp[2] == 'pending' else "✅" if comp[2] == 'approved' else "❌"
            status_text = "ОЖИДАЕТ" if comp[2] == 'pending' else "ОДОБРЕНА" if comp[2] == 'approved' else "ОТКЛОНЕНА"
            date_str = datetime.datetime.strptime(comp[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m')
            
            text += f"{status_icon} #{comp[0]} - {date_str} - {status_text}"
            
            if comp[4]:  # если есть дата решения
                decision_date = datetime.datetime.strptime(comp[4], '%Y-%m-%d %H:%M:%S').strftime('%d.%m')
                text += f" ({decision_date})"
            
            if comp[5]:  # если есть username админа
                text += f" 👮 @{comp[5]}"
            
            text += "\n"
    
    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")
    back_markup.add(back_btn)
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main(call):
    start_command(call.message)

# ===== ПАНЕЛЬ АДМИНИСТРАТОРА =====

@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel_callback(call):
    if is_admin(call.from_user.id):
        show_admin_menu(call.message)
    else:
        bot.answer_callback_query(call.id, "⛔ У вас нет доступа!")

@bot.message_handler(commands=['admin'])
def admin_command(message):
    if is_admin(message.from_user.id):
        show_admin_menu(message)
    else:
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой команде.")

def show_admin_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    stats_btn = types.InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats")
    pending_btn = types.InlineKeyboardButton("⏳ ОЖИДАЮЩИЕ", callback_data="admin_pending")
    all_complaints_btn = types.InlineKeyboardButton("📋 ВСЕ ЖАЛОБЫ", callback_data="admin_all")
    markup.add(stats_btn, pending_btn, all_complaints_btn)
    
    bot.send_message(message.chat.id, "👮 ПАНЕЛЬ АДМИНИСТРАТОРА", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if not is_admin(call.from_user.id):
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

📈 Обработано: {approved + rejected} из {total}
"""
    
    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin")
    back_markup.add(back_btn)
    
    bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_pending")
def admin_pending(call):
    if not is_admin(call.from_user.id):
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
    """Показать все жалобы - включая обработанные"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    
    cursor.execute('''
    SELECT id, status, first_name, created_at, decision_time, admin_username
    FROM complaints 
    ORDER BY id DESC 
    LIMIT 20
    ''')
    
    all_complaints = cursor.fetchall()
    
    text = "📋 ПОСЛЕДНИЕ 20 ЖАЛОБ:\n\n"
    for comp in all_complaints:
        status_icon = "⏳" if comp[1] == 'pending' else "✅" if comp[1] == 'approved' else "❌"
        date_str = datetime.datetime.strptime(comp[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m')
        
        text += f"{status_icon} #{comp[0]} - 👤 {comp[2]} - 📅 {date_str}"
        
        if comp[4]:  # если есть дата решения
            decision_date = datetime.datetime.strptime(comp[4], '%Y-%m-%d %H:%M:%S').strftime('%d.%m')
            text += f" (решено: {decision_date})"
        
        if comp[5]:  # если есть админ
            text += f" 👮 @{comp[5]}"
        
        text += "\n"
    
    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin")
    back_markup.add(back_btn)
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_admin")
def back_to_admin(call):
    if is_admin(call.from_user.id):
        show_admin_menu(call.message)

# ===== ЗАПУСК БОТА =====
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 БОТ ДЛЯ ПРИЕМА ЖАЛОБ ЗАПУЩЕН")
    print(f"👥 Администраторов: {len(ADMIN_IDS)}")
    print(f"👮 ID администраторов: {ADMIN_IDS}")
    print("=" * 50)
    
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"❌ Ошибка: {e}")


