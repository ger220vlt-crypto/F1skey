import sqlite3
import os
import telebot
from telebot import types
import datetime
import time

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8523088853:AAHEHLFYK9T6AqHERXYlK5Qn7rmqajEvegQ"  # Замените на токен от @BotFather

# ===== СПИСОК АДМИНИСТРАТОРОВ =====
ADMIN_IDS = [
    7200109509,  # ID первого админа
    1232171882,
    523416060, # ID второго админа
]

# ===== АНТИСПАМ СИСТЕМА =====
last_complaint_time = {}
SPAM_LIMIT = 3  # Максимум 3 жалобы
COOLDOWN_MINUTES = 5  # Ожидание 5 минут после лимита

# ===== БАЗА ДАННЫХ =====
os.makedirs('db', exist_ok=True)
conn = sqlite3.connect('db/complaints.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы
cursor.execute('''
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    first_name TEXT,
    category TEXT,
    complaint_text TEXT,
    status TEXT DEFAULT 'pending',
    admin_id INTEGER,
    admin_response TEXT DEFAULT '',
    decision_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()


# Проверяем и добавляем колонки если их нет
def check_and_fix_database():
    try:
        cursor.execute("SELECT category FROM complaints LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE complaints ADD COLUMN category TEXT")

    try:
        cursor.execute("SELECT admin_response FROM complaints LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE complaints ADD COLUMN admin_response TEXT DEFAULT ''")

    conn.commit()


check_and_fix_database()

# ===== ИНИЦИАЛИЗАЦИЯ БОТА =====
bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}


# ===== ФУНКЦИИ =====

def is_admin(user_id):
    return user_id in ADMIN_IDS


def check_spam_and_get_wait_time(user_id):
    """Проверяет антиспам и возвращает сколько ждать до следующей жалобы"""
    current_time = time.time()

    if user_id not in last_complaint_time:
        last_complaint_time[user_id] = []

    # Удаляем старые записи (старше 1 часа)
    last_complaint_time[user_id] = [
        t for t in last_complaint_time[user_id]
        if current_time - t < 3600  # 1 час
    ]

    # Если достигли лимита
    if len(last_complaint_time[user_id]) >= SPAM_LIMIT:
        # Берем время самой старой жалобы в пределах лимита
        oldest_complaint = last_complaint_time[user_id][0]
        cooldown_end = oldest_complaint + (COOLDOWN_MINUTES * 60)
        wait_seconds = max(0, cooldown_end - current_time)

        if wait_seconds > 0:
            minutes = int(wait_seconds // 60)
            seconds = int(wait_seconds % 60)
            return False, f"⏰ Вы отправили {SPAM_LIMIT} жалоб. Подождите {minutes} минут {seconds} секунд."
        else:
            # Если время ожидания прошло, очищаем список
            last_complaint_time[user_id] = []
            return True, ""

    return True, ""


def get_remaining_complaints(user_id):
    """Возвращает сколько жалоб осталось можно отправить"""
    if user_id not in last_complaint_time:
        return SPAM_LIMIT

    return max(0, SPAM_LIMIT - len(last_complaint_time[user_id]))


# ===== ОСНОВНЫЕ ФУНКЦИИ =====

@bot.message_handler(commands=['start'])
def start_command(message):
    user_states[message.chat.id] = {'state': None}

    markup = types.InlineKeyboardMarkup()
    new_complaint_btn = types.InlineKeyboardButton("📝 НАПИСАТЬ ЖАЛОБУ", callback_data="new_complaint")
    my_complaints_btn = types.InlineKeyboardButton("📋 МОИ ЖАЛОБЫ", callback_data="my_complaints")
    markup.add(new_complaint_btn)
    markup.add(my_complaints_btn)

    # Показываем сколько жалоб осталось
    remaining = get_remaining_complaints(message.from_user.id)
    status_text = f"\n📊 Осталось жалоб сегодня: {remaining}/{SPAM_LIMIT}"

    text = f"""
🔔 БОТ ДЛЯ ПРИЕМА ЗАЯВОК

Здесь вы можете оставить жалобы и предложения по улучшению студенческой жизни.

Ваши обращения будут рассмотрены студенческим активом и вынесены на рассмотрение администрации колледжа. 

Мы гарантируем конфиденциальность:
{status_text}
"""

    if is_admin(message.from_user.id):
        admin_btn = types.InlineKeyboardButton("👮 АДМИН ПАНЕЛЬ", callback_data="admin_panel")
        markup.add(admin_btn)

    bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "new_complaint")
def start_new_complaint(call):
    # Проверяем антиспам перед началом
    spam_ok, spam_msg = check_spam_and_get_wait_time(call.from_user.id)

    if not spam_ok:
        bot.answer_callback_query(call.id, spam_msg, show_alert=True)
        return

    user_states[call.message.chat.id] = {'state': 'waiting_category'}

    markup = types.InlineKeyboardMarkup(row_width=2)

    # Кнопки категорий
    btn1 = types.InlineKeyboardButton("ГК", callback_data="category_ГК")
    btn2 = types.InlineKeyboardButton("УК1", callback_data="category_УК1")
    btn3 = types.InlineKeyboardButton("УК2", callback_data="category_УК2")
    btn4 = types.InlineKeyboardButton("УК3", callback_data="category_УК3")

    markup.add(btn1, btn2, btn3, btn4)

    # Показываем сколько осталось жалоб
    remaining = get_remaining_complaints(call.from_user.id)
    status_text = f"📊 Осталось жалоб: {remaining}/{SPAM_LIMIT}"

    cancel_btn = types.InlineKeyboardButton("❌ ОТМЕНИТЬ", callback_data="cancel_complaint")
    markup.add(cancel_btn)

    bot.edit_message_text(
        f"📋 ВЫБЕРИТЕ КАТЕГОРИЮ:\n\n{status_text}",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('category_'))
def select_category(call):
    category = call.data.split('_')[1]

    user_states[call.message.chat.id] = {
        'state': 'waiting_complaint',
        'category': category
    }

    # Показываем сколько осталось жалоб
    remaining = get_remaining_complaints(call.from_user.id)
    status_text = f"📊 Осталось жалоб: {remaining}/{SPAM_LIMIT}"

    bot.edit_message_text(
        f"📝 НАПИШИТЕ ЖАЛОБУ ({category}):\n\n"
        f"• Минимум 20 символов\n"
        f"• Будьте конкретны\n"
        f"• Опишите проблему подробно\n\n"
        f"{status_text}",
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

    bot.edit_message_text("❌ Отменено", call.message.chat.id, call.message.message_id)
    start_command(call.message)


@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_complaint')
def save_complaint(message):
    user_id = message.from_user.id

    # Проверка антиспама
    spam_ok, spam_msg = check_spam_and_get_wait_time(user_id)
    if not spam_ok:
        bot.send_message(message.chat.id, spam_msg)
        return

    complaint_text = message.text.strip()

    if len(complaint_text) < 20:
        bot.send_message(message.chat.id, "❌ Минимум 20 символов.")
        return

    user_data = user_states[message.chat.id]
    category = user_data.get('category', 'ГК')

    try:
        cursor.execute('''
        INSERT INTO complaints (user_id, username, first_name, category, complaint_text)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            category,
            complaint_text
        ))
        complaint_id = cursor.lastrowid
        conn.commit()

        # Добавляем время отправки для антиспама
        current_time = time.time()
        if user_id not in last_complaint_time:
            last_complaint_time[user_id] = []
        last_complaint_time[user_id].append(current_time)

        # Обновляем количество оставшихся жалоб
        remaining = get_remaining_complaints(user_id)
        remaining_text = f"📊 Осталось жалоб: {remaining}/{SPAM_LIMIT}"

        user_markup = types.InlineKeyboardMarkup()
        new_complaint_btn = types.InlineKeyboardButton("📝 НОВАЯ ЖАЛОБА", callback_data="new_complaint")
        status_btn = types.InlineKeyboardButton("📋 МОИ ЖАЛОБЫ", callback_data="my_complaints")
        user_markup.add(new_complaint_btn, status_btn)

        confirm_text = f"""
✅ ЖАЛОБА ПРИНЯТА!

📄 #{complaint_id} ({category})
📅 {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

🔄 Статус: ⏳ ОЖИДАЕТ РЕШЕНИЯ

{remaining_text}
"""
        bot.send_message(message.chat.id, confirm_text, reply_markup=user_markup)

        # Отправляем администраторам с кнопкой ОТВЕТИТЬ
        send_complaint_to_admins(complaint_id, message.from_user, category, complaint_text)
        user_states[message.chat.id] = {'state': None}

    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка при сохранении")
        print(f"Error: {e}")


def send_complaint_to_admins(complaint_id, user, category, complaint_text):
    """Отправляет жалобу всем администраторам"""
    admin_text = f"""
🚨 НОВАЯ ЖАЛОБА #{complaint_id}

🏷️ КАТЕГОРИЯ: {category}
👤 ОТ: {user.first_name}
📱 @{user.username or 'нет username'}
🆔 ID: {user.id}
📅 {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

📝 ТЕКСТ:
{complaint_text}
"""

    markup = types.InlineKeyboardMarkup(row_width=2)
    approve_btn = types.InlineKeyboardButton("✅ ОДОБРИТЬ", callback_data=f"approve_{complaint_id}")
    reject_btn = types.InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_{complaint_id}")
    respond_btn = types.InlineKeyboardButton("💬 ОТВЕТИТЬ", callback_data=f"respond_{complaint_id}")
    markup.add(approve_btn, reject_btn, respond_btn)

    # Отправляем всем администраторам
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, admin_text, reply_markup=markup)
        except Exception as e:
            print(f"Error sending to admin {admin_id}: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_', 'respond_')))
def handle_admin_action(call):
    """Обработка действий администратора"""
    complaint_id = int(call.data.split('_')[1])
    action = call.data.split('_')[0]

    # Проверяем что пользователь админ
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return

    if action in ['approve', 'reject']:
        # Одобрение или отклонение жалобы
        handle_decision(call, complaint_id, action)
    elif action == 'respond':
        # Ответ пользователю
        handle_response_request(call, complaint_id)


def handle_decision(call, complaint_id, action):
    """Обработка решения (одобрить/отклонить) - СООБЩЕНИЕ НЕ ПРОПАДАЕТ У АДМИНОВ"""
    cursor.execute('''
    SELECT user_id, category, complaint_text, status, created_at, first_name
    FROM complaints WHERE id = ?
    ''', (complaint_id,))

    complaint = cursor.fetchone()

    if not complaint:
        bot.answer_callback_query(call.id, "❌ Жалоба не найдена")
        return

    user_id, category, complaint_text, current_status, created_at, first_name = complaint

    # Если уже обработана, просто обновляем статус
    new_status = 'approved' if action == 'approve' else 'rejected'

    # Обновляем статус в базе
    cursor.execute('''
    UPDATE complaints 
    SET status = ?, admin_id = ?, decision_time = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (
        new_status,
        call.from_user.id,
        complaint_id
    ))
    conn.commit()

    # Уведомляем пользователя о решении
    decision_date = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    if action == 'approve':
        decision_text = f"""
✅ ЖАЛОБА ОДОБРЕНА

📄 #{complaint_id} ({category})
📅 Дата решения: {decision_date}
"""
    else:
        decision_text = f"""
❌ ЖАЛОБА ОТКЛОНЕНА

📄 #{complaint_id} ({category})
📅 Дата решения: {decision_date}
"""

    try:
        # Отправляем уведомление только если статус изменился
        if current_status != new_status:
            bot.send_message(user_id, decision_text)
    except Exception as e:
        print(f"Error notifying user: {e}")

    # ОБНОВЛЯЕМ СООБЩЕНИЕ У АДМИНА (НЕ УДАЛЯЕМ!)
    status_text = "ОДОБРЕНА ✅" if action == 'approve' else "ОТКЛОНЕНА ❌"
    created_date = datetime.datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')

    updated_text = f"""
📋 ЖАЛОБА #{complaint_id} - {status_text}

🏷️ Категория: {category}
👤 От: {first_name}
📅 Подана: {created_date}
📅 Решена: {decision_date}
👮 Решил: Администратор

📝 Текст жалобы:
{complaint_text[:300]}{'...' if len(complaint_text) > 300 else ''}
"""

    # СОХРАНЯЕМ ВСЕ ФУНКЦИОНАЛЬНЫЕ КНОПКИ
    markup = types.InlineKeyboardMarkup(row_width=2)

    # Кнопки остаются активными даже после решения
    if action == 'approve':
        # Если одобрили, можно отклонить и наоборот
        reject_btn = types.InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_{complaint_id}")
        markup.add(reject_btn)
    else:
        approve_btn = types.InlineKeyboardButton("✅ ОДОБРИТЬ", callback_data=f"approve_{complaint_id}")
        markup.add(approve_btn)

    # Кнопка ответа всегда доступна
    respond_btn = types.InlineKeyboardButton("💬 ОТВЕТИТЬ", callback_data=f"respond_{complaint_id}")
    markup.add(respond_btn)

    # Кнопка просмотра деталей
    view_btn = types.InlineKeyboardButton("👁️‍🗨️ ПРОСМОТР", callback_data=f"view_{complaint_id}")
    markup.add(view_btn)

    # НЕ УДАЛЯЕМ сообщение, а редактируем его
    try:
        bot.edit_message_text(
            updated_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error editing message: {e}")

    bot.answer_callback_query(call.id, f"✅ Статус обновлен: {status_text}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('view_'))
def view_complaint_details(call):
    """Просмотр деталей жалобы"""
    complaint_id = int(call.data.split('_')[1])

    cursor.execute('''
    SELECT category, complaint_text, status, created_at, 
           decision_time, admin_response, first_name
    FROM complaints WHERE id = ?
    ''', (complaint_id,))

    complaint = cursor.fetchone()

    if not complaint:
        bot.answer_callback_query(call.id, "❌ Жалоба не найдена")
        return

    category, complaint_text, status, created_at, decision_time, admin_response, first_name = complaint

    status_icon = "⏳" if status == 'pending' else "✅" if status == 'approved' else "❌"
    status_text = "ОЖИДАЕТ" if status == 'pending' else "ОДОБРЕНА" if status == 'approved' else "ОТКЛОНЕНА"
    created_date = datetime.datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')

    details_text = f"""
📋 ДЕТАЛИ ЖАЛОБЫ #{complaint_id}

{status_icon} Статус: {status_text}
🏷️ Категория: {category}
👤 Отправитель: {first_name}
📅 Дата подачи: {created_date}
"""

    if decision_time:
        decision_date = datetime.datetime.strptime(decision_time, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
        details_text += f"📅 Дата решения: {decision_date}\n"

    details_text += f"""
📝 Текст жалобы:
{complaint_text}
"""

    if admin_response:
        details_text += f"""
💬 Ответ администратора:
{admin_response}
"""

    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД К ЖАЛОБЕ", callback_data=f"back_to_complaint_{complaint_id}")
    back_markup.add(back_btn)

    bot.edit_message_text(
        details_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=back_markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_complaint_'))
def back_to_complaint(call):
    """Возврат к жалобе из просмотра деталей"""
    complaint_id = int(call.data.split('_')[3])

    cursor.execute('''
    SELECT category, complaint_text, status, created_at, first_name, decision_time
    FROM complaints WHERE id = ?
    ''', (complaint_id,))

    complaint = cursor.fetchone()

    if not complaint:
        bot.answer_callback_query(call.id, "❌ Жалоба не найдена")
        return

    category, complaint_text, status, created_at, first_name, decision_time = complaint
    status_text = "ОДОБРЕНА ✅" if status == 'approved' else "ОТКЛОНЕНА ❌" if status == 'rejected' else "ОЖИДАЕТ ⏳"
    created_date = datetime.datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')

    if decision_time:
        decision_date = datetime.datetime.strptime(decision_time, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
        date_info = f"📅 Подана: {created_date}\n📅 Решена: {decision_date}"
    else:
        date_info = f"📅 Подана: {created_date}"

    updated_text = f"""
📋 ЖАЛОБА #{complaint_id} - {status_text}

🏷️ Категория: {category}
👤 От: {first_name}
{date_info}

📝 Текст жалобы:
{complaint_text[:300]}{'...' if len(complaint_text) > 300 else ''}
"""

    markup = types.InlineKeyboardMarkup(row_width=2)

    # В зависимости от статуса показываем разные кнопки
    if status == 'pending':
        approve_btn = types.InlineKeyboardButton("✅ ОДОБРИТЬ", callback_data=f"approve_{complaint_id}")
        reject_btn = types.InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_{complaint_id}")
        markup.add(approve_btn, reject_btn)
    elif status == 'approved':
        reject_btn = types.InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_{complaint_id}")
        markup.add(reject_btn)
    else:  # rejected
        approve_btn = types.InlineKeyboardButton("✅ ОДОБРИТЬ", callback_data=f"approve_{complaint_id}")
        markup.add(approve_btn)

    # Кнопка ответа всегда доступна
    respond_btn = types.InlineKeyboardButton("💬 ОТВЕТИТЬ", callback_data=f"respond_{complaint_id}")
    markup.add(respond_btn)

    # Кнопка просмотра деталей
    view_btn = types.InlineKeyboardButton("👁️‍🗨️ ПРОСМОТР", callback_data=f"view_{complaint_id}")
    markup.add(view_btn)

    bot.edit_message_text(
        updated_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )


def handle_response_request(call, complaint_id):
    """Запрос на ответ пользователю"""
    cursor.execute('SELECT user_id, username, first_name, category FROM complaints WHERE id = ?', (complaint_id,))
    complaint = cursor.fetchone()

    if not complaint:
        bot.answer_callback_query(call.id, "❌ Жалоба не найдена")
        return

    user_id, username, first_name, category = complaint

    # Сохраняем состояние для ответа
    user_states[call.message.chat.id] = {
        'state': 'waiting_admin_response',
        'complaint_id': complaint_id,
        'user_id': user_id,
        'first_name': first_name,
        'category': category
    }

    bot.answer_callback_query(call.id, "✍️ Напишите ответ пользователю")

    # Просим админа написать ответ
    response_text = f"""
💬 ОТВЕТ ПОЛЬЗОВАТЕЛЮ

Жалоба #{complaint_id} ({category})
Пользователь: {first_name}

Напишите ваш ответ (минимум 10 символов):
"""

    cancel_markup = types.InlineKeyboardMarkup()
    cancel_btn = types.InlineKeyboardButton("❌ ОТМЕНИТЬ ОТВЕТ", callback_data="cancel_response")
    cancel_markup.add(cancel_btn)

    bot.send_message(call.message.chat.id, response_text, reply_markup=cancel_markup)


@bot.callback_query_handler(func=lambda call: call.data == "cancel_response")
def cancel_response(call):
    """Отмена ответа"""
    if call.message.chat.id in user_states:
        user_states[call.message.chat.id] = {'state': None}

    bot.answer_callback_query(call.id, "❌ Ответ отменен")
    bot.send_message(call.message.chat.id, "❌ Ответ отменен")


@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_admin_response')
def send_admin_response(message):
    """Отправка ответа от администратора пользователю (БЕЗ username админа)"""
    user_data = user_states[message.chat.id]
    complaint_id = user_data['complaint_id']
    user_id = user_data['user_id']
    first_name = user_data['first_name']
    category = user_data['category']

    admin_response = message.text.strip()

    if len(admin_response) < 10:
        bot.send_message(message.chat.id, "❌ Ответ должен быть не менее 10 символов.")
        return

    try:
        # Сохраняем ответ в базе (БЕЗ username админа)
        cursor.execute('''
        UPDATE complaints 
        SET admin_response = ?, admin_id = ?
        WHERE id = ?
        ''', (
            admin_response,
            message.from_user.id,
            complaint_id
        ))
        conn.commit()

        # Отправляем ответ пользователю (БЕЗ username админа)
        response_to_user = f"""
💬 ОТВЕТ НА ВАШУ ЖАЛОБУ

📄 Номер жалобы: #{complaint_id} ({category})
📅 {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

📝 Ответ администратора:
{admin_response}
"""

        try:
            bot.send_message(user_id, response_to_user)
            bot.send_message(message.chat.id, f"✅ Ответ отправлен пользователю {first_name}")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Не удалось отправить ответ пользователю")

        # Сбрасываем состояние
        user_states[message.chat.id] = {'state': None}

    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка при сохранении ответа")
        print(f"Error: {e}")


# ===== МОИ ЖАЛОБЫ =====

@bot.callback_query_handler(func=lambda call: call.data == "my_complaints")
def show_my_complaints(call):
    """Показать жалобы пользователя с ответами администраторов - ВСЕ жалобы"""
    cursor.execute('''
    SELECT id, category, status, created_at, admin_response, decision_time
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
            date_str = datetime.datetime.strptime(comp[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            text += f"{status_icon} #{comp[0]} ({comp[1]}) - {date_str}"

            if comp[5]:  # если есть дата решения
                decision_date = datetime.datetime.strptime(comp[5], '%Y-%m-%d %H:%M:%S').strftime('%d.%m')
                text += f" [решено {decision_date}]"

            # Показываем иконку если есть ответ от админа
            if comp[4]:  # если есть ответ админа
                text += " 💬"

            text += "\n"

    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")
    back_markup.add(back_btn)

    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)


@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main(call):
    start_command(call.message)


# ===== АДМИН ПАНЕЛЬ =====

@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel_callback(call):
    if is_admin(call.from_user.id):
        show_admin_menu(call.message)
    else:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")


@bot.message_handler(commands=['admin'])
def admin_command(message):
    if is_admin(message.from_user.id):
        show_admin_menu(message)
    else:
        bot.send_message(message.chat.id, "⛔ Нет доступа")


def show_admin_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    stats_btn = types.InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats")
    pending_btn = types.InlineKeyboardButton("⏳ ОЖИДАЮЩИЕ", callback_data="admin_pending")
    all_complaints_btn = types.InlineKeyboardButton("📋 ВСЕ ЖАЛОБЫ", callback_data="admin_all")
    markup.add(stats_btn, pending_btn, all_complaints_btn)

    bot.send_message(message.chat.id, "👮 АДМИН ПАНЕЛЬ", reply_markup=markup)


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

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE admin_response != ''")
    responded = cursor.fetchone()[0]

    stats_text = f"""
📊 СТАТИСТИКА:

📨 Всего жалоб: {total}
⏳ Ожидают решения: {pending}
✅ Одобрено: {approved}
❌ Отклонено: {rejected}
💬 С ответами: {responded}
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
    SELECT id, category, first_name, created_at 
    FROM complaints 
    WHERE status = 'pending' 
    ORDER BY id DESC 
    LIMIT 20
    ''')

    pending = cursor.fetchall()

    if not pending:
        text = "📭 Нет жалоб ожидающих решения."
    else:
        text = "⏳ ОЖИДАЮЩИЕ РЕШЕНИЯ:\n\n"
        for comp in pending:
            date_str = datetime.datetime.strptime(comp[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m %H:%M')
            text += f"#{comp[0]} ({comp[1]}) - 👤 {comp[2]} - 🕐 {date_str}\n"

    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin")
    back_markup.add(back_btn)

    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)


@bot.callback_query_handler(func=lambda call: call.data == "admin_all")
def admin_all(call):
    """Показать ВСЕ жалобы - включая обработанные"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return

    cursor.execute('''
    SELECT id, category, status, created_at, first_name, decision_time
    FROM complaints 
    ORDER BY id DESC 
    LIMIT 20
    ''')

    all_complaints = cursor.fetchall()

    text = "📋 ПОСЛЕДНИЕ 20 ЖАЛОБ:\n\n"
    for comp in all_complaints:
        status_icon = "⏳" if comp[2] == 'pending' else "✅" if comp[2] == 'approved' else "❌"
        date_str = datetime.datetime.strptime(comp[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m')

        text += f"{status_icon} #{comp[0]} ({comp[1]}) - 👤 {comp[4]} - 📅 {date_str}"

        if comp[5]:  # если есть дата решения
            text += " ✅"

        text += "\n"

    back_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin")
    back_markup.add(back_btn)

    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)


@bot.callback_query_handler(func=lambda call: call.data == "back_to_admin")
def back_to_admin(call):
    if is_admin(call.from_user.id):
        show_admin_menu(call.message)


# ===== КОМАНДА ДЛЯ ПРОВЕРКИ ОСТАВШИХСЯ ЖАЛОБ =====

@bot.message_handler(commands=['status'])
def status_command(message):
    """Показывает сколько жалоб осталось отправить"""
    remaining = get_remaining_complaints(message.from_user.id)

    if remaining == 0:
        # Если лимит исчерпан, показываем сколько ждать
        if message.from_user.id in last_complaint_time and last_complaint_time[message.from_user.id]:
            oldest_complaint = last_complaint_time[message.from_user.id][0]
            cooldown_end = oldest_complaint + (COOLDOWN_MINUTES * 60)
            wait_seconds = max(0, cooldown_end - time.time())

            if wait_seconds > 0:
                minutes = int(wait_seconds // 60)
                seconds = int(wait_seconds % 60)
                text = f"⏰ Лимит исчерпан. Подождите {minutes} минут {seconds} секунд."
            else:
                text = f"📊 Осталось жалоб: {remaining}/{SPAM_LIMIT}"
        else:
            text = f"📊 Осталось жалоб: {remaining}/{SPAM_LIMIT}"
    else:
        text = f"📊 Осталось жалоб: {remaining}/{SPAM_LIMIT}"

    bot.send_message(message.chat.id, text)


# ===== ЗАПУСК =====
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 БОТ ДЛЯ ЖАЛОБ - ОБРАЩЕНИЯ НЕ ПРОПАДАЮТ")
    print(f"👥 Администраторов: {len(ADMIN_IDS)}")
    print(f"📊 Лимит жалоб: {SPAM_LIMIT} в {COOLDOWN_MINUTES} минут")
    print("=" * 50)

    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
