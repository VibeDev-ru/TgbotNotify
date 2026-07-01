import telebot
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import re
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import pytz
from datetime import datetime
import os

# ======= НАСТРОЙКИ =======
BOT_TOKEN = "8736477830:AAEI1KvzhpoeJxTD1cCT8sFNFwIYUjTflPM"
DB_NAME = "reminders.db"
CHANNEL_ID = "@VibeDev_rus"  # ID вашего канала
# ========================

bot = telebot.TeleBot(BOT_TOKEN)

# Словарь для хранения временных данных пользователей
user_data = {}

# Кэш для проверки подписки (чтобы не спамить запросами)
subscription_cache = {}

# Часовые пояса
TIMEZONES = {
    'МСК': 'Europe/Moscow',
    'ЕКБ': 'Asia/Yekaterinburg',
    'НСК': 'Asia/Novosibirsk',
    'КРАС': 'Asia/Krasnoyarsk',
    'ИРК': 'Asia/Irkutsk',
    'ВЛД': 'Asia/Vladivostok',
    'КАМ': 'Asia/Kamchatka',
    'КИЕВ': 'Europe/Kiev',
    'МИНСК': 'Europe/Minsk'
}

def get_main_keyboard():
    """Главное меню с кнопками"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("➕ Новая напоминалка"),
        KeyboardButton("📋 Все напоминалки")
    )
    keyboard.add(
        KeyboardButton("🗑️ Удалить напоминалку"),
        KeyboardButton("❌ Отменить создание")
    )
    return keyboard

def get_subscribe_keyboard():
    """Клавиатура для подписки на канал"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📢 Подписаться на канал", url="https://t.me/VibeDev_rus")
    )
    keyboard.add(
        InlineKeyboardButton("✅ Проверить подписку", callback_data="check_subscription")
    )
    return keyboard

def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add(KeyboardButton("❌ Отменить создание"))
    return keyboard

def init_db():
    """Инициализация базы данных с проверкой и обновлением структуры"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reminders'")
        table_exists = c.fetchone()
        
        if not table_exists:
            print("📝 Создаю таблицу reminders...")
            c.execute('''CREATE TABLE reminders (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER,
                         reminder_time TEXT,
                         text TEXT,
                         spam_interval INTEGER,
                         is_done BOOLEAN DEFAULT 0,
                         last_spam_time TEXT,
                         repeat_type TEXT DEFAULT 'none',
                         timezone TEXT DEFAULT 'Europe/Moscow'
                      )''')
            print("✅ Таблица создана")
        else:
            print("📝 Таблица существует, проверяю структуру...")
            try:
                c.execute("SELECT repeat_type FROM reminders LIMIT 1")
            except sqlite3.OperationalError:
                c.execute("ALTER TABLE reminders ADD COLUMN repeat_type TEXT DEFAULT 'none'")
                print("✅ Добавлена колонка repeat_type")
            
            try:
                c.execute("SELECT timezone FROM reminders LIMIT 1")
            except sqlite3.OperationalError:
                c.execute("ALTER TABLE reminders ADD COLUMN timezone TEXT DEFAULT 'Europe/Moscow'")
                print("✅ Добавлена колонка timezone")
        
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
        return True
    except Exception as e:
        print(f"❌ Ошибка при инициализации БД: {e}")
        return False

def get_db_connection():
    """Получение соединения с БД с проверкой"""
    try:
        conn = sqlite3.connect(DB_NAME)
        return conn
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return None

def check_subscription(user_id):
    """Проверяет, подписан ли пользователь на канал"""
    try:
        # Проверяем кэш (не чаще чем раз в 10 секунд)
        current_time = time.time()
        if user_id in subscription_cache:
            cached_status, cached_time = subscription_cache[user_id]
            if current_time - cached_time < 10:  # 10 секунд кэша
                return cached_status
        
        # Получаем статус пользователя в канале
        try:
            status = bot.get_chat_member(CHANNEL_ID, user_id).status
            is_subscribed = status in ['member', 'administrator', 'creator']
        except Exception as e:
            print(f"⚠️ Ошибка при проверке подписки для {user_id}: {e}")
            # Если бот не может проверить (например, нет прав), пропускаем
            is_subscribed = True
        
        # Сохраняем в кэш
        subscription_cache[user_id] = (is_subscribed, current_time)
        
        return is_subscribed
    except Exception as e:
        print(f"❌ Ошибка в check_subscription: {e}")
        return True  # В случае ошибки даем доступ

def add_reminder(user_id, reminder_time, text, spam_interval, repeat_type, timezone):
    try:
        conn = get_db_connection()
        if not conn:
            return False
        c = conn.cursor()
        c.execute("""INSERT INTO reminders 
                     (user_id, reminder_time, text, spam_interval, last_spam_time, repeat_type, timezone) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (user_id, reminder_time, text, spam_interval, 
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"), repeat_type, timezone))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка при добавлении напоминания: {e}")
        return False

def get_active_reminders():
    try:
        conn = get_db_connection()
        if not conn:
            return []
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("""SELECT id, user_id, text, spam_interval, last_spam_time, repeat_type, timezone, reminder_time
                     FROM reminders WHERE reminder_time <= ? AND is_done = 0""", (now,))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ Ошибка при получении активных напоминаний: {e}")
        return []

def mark_reminder_done(reminder_id):
    try:
        conn = get_db_connection()
        if not conn:
            return False
        c = conn.cursor()
        c.execute("UPDATE reminders SET is_done = 1 WHERE id = ?", (reminder_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка при отметке напоминания как выполненного: {e}")
        return False

def update_last_spam_time(reminder_id):
    try:
        conn = get_db_connection()
        if not conn:
            return False
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE reminders SET last_spam_time = ? WHERE id = ?", (now, reminder_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка при обновлении времени спама: {e}")
        return False

def get_spam_keyboard(reminder_id):
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton("✅ Прочитано", callback_data=f"done_{reminder_id}")
    keyboard.add(button)
    return keyboard

def get_repeat_keyboard(reminder_id):
    """Клавиатура для выбора: продолжать повторять или остановить"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔄 Продолжить", callback_data=f"repeat_yes_{reminder_id}"),
        InlineKeyboardButton("⏹️ Остановить", callback_data=f"repeat_no_{reminder_id}")
    )
    return keyboard

def get_repeat_type_keyboard():
    """Клавиатура для выбора типа повторения"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📆 Каждый месяц"),
        KeyboardButton("📅 Каждую неделю")
    )
    keyboard.add(
        KeyboardButton("🔄 Каждый день"),
        KeyboardButton("❌ Не повторять")
    )
    keyboard.add(
        KeyboardButton("❌ Отменить создание")
    )
    return keyboard

def get_timezone_keyboard():
    """Клавиатура для выбора часового пояса"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("МСК (UTC+3)"),
        KeyboardButton("ЕКБ (UTC+5)"),
        KeyboardButton("НСК (UTC+7)")
    )
    keyboard.add(
        KeyboardButton("КРАС (UTC+7)"),
        KeyboardButton("ИРК (UTC+8)"),
        KeyboardButton("ВЛД (UTC+10)")
    )
    keyboard.add(
        KeyboardButton("КАМ (UTC+12)"),
        KeyboardButton("КИЕВ (UTC+2)"),
        KeyboardButton("МИНСК (UTC+3)")
    )
    keyboard.add(
        KeyboardButton("❌ Отменить создание")
    )
    return keyboard

def get_interval_keyboard():
    """Клавиатура для выбора интервала спама"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=3)
    keyboard.add(
        KeyboardButton("1 минута"),
        KeyboardButton("5 минут"),
        KeyboardButton("10 минут")
    )
    keyboard.add(
        KeyboardButton("30 минут"),
        KeyboardButton("1 час"),
        KeyboardButton("❌ Отменить создание")
    )
    return keyboard

def parse_timezone(tz_text):
    """Парсит часовой пояс из текста пользователя"""
    tz_text = tz_text.strip().upper()
    
    for key, value in TIMEZONES.items():
        if key in tz_text:
            return value
    
    utc_match = re.search(r'UTC([+-])(\d+)', tz_text)
    if utc_match:
        sign = utc_match.group(1)
        hours = int(utc_match.group(2))
        
        if hours > 12:
            hours = 12
        
        if sign == '+':
            return f'Etc/GMT-{hours}'
        else:
            return f'Etc/GMT+{hours}'
    
    simple_match = re.search(r'([+-])(\d+)', tz_text)
    if simple_match:
        sign = simple_match.group(1)
        hours = int(simple_match.group(2))
        
        if hours > 12:
            hours = 12
        
        if sign == '+':
            return f'Etc/GMT-{hours}'
        else:
            return f'Etc/GMT+{hours}'
    
    return None

def parse_custom_datetime(date_str, timezone_str='Europe/Moscow'):
    """Парсит дату в формате 'ДД ММ ГГ ЧЧ ММ' с учетом часового пояса"""
    try:
        parts = date_str.strip().split()
        if len(parts) != 5:
            return None, "Неверный формат! Нужно: ДД ММ ГГ ЧЧ ММ"
        
        day, month, year, hour, minute = parts
        
        if not (day.isdigit() and month.isdigit() and year.isdigit() and hour.isdigit() and minute.isdigit()):
            return None, "Все значения должны быть числами!"
        
        day = int(day)
        month = int(month)
        year = int(year) + 2000
        hour = int(hour)
        minute = int(minute)
        
        if not (1 <= day <= 31):
            return None, "День должен быть от 1 до 31"
        if not (1 <= month <= 12):
            return None, "Месяц должен быть от 1 до 12"
        if not (0 <= hour <= 23):
            return None, "Час должен быть от 0 до 23"
        if not (0 <= minute <= 59):
            return None, "Минуты должны быть от 0 до 59"
        
        dt = datetime(year, month, day, hour, minute)
        
        tz = pytz.timezone(timezone_str)
        dt_with_tz = tz.localize(dt)
        dt_utc = dt_with_tz.astimezone(pytz.UTC)
        
        return dt_utc.replace(tzinfo=None), None
        
    except ValueError as e:
        return None, f"Ошибка: {e}"
    except Exception as e:
        return None, f"Ошибка: {e}"

def get_next_reminder_time(reminder_time, repeat_type, timezone_str):
    """Вычисляет следующее время напоминания в зависимости от типа повторения"""
    try:
        tz = pytz.timezone(timezone_str)
        
        dt_utc = datetime.strptime(reminder_time, "%Y-%m-%d %H:%M")
        dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
        dt_local = dt_utc.astimezone(tz)
        
        if repeat_type == 'daily':
            next_dt = dt_local + timedelta(days=1)
        elif repeat_type == 'weekly':
            next_dt = dt_local + timedelta(weeks=1)
        elif repeat_type == 'monthly':
            if dt_local.month == 12:
                next_dt = dt_local.replace(year=dt_local.year + 1, month=1)
            else:
                next_dt = dt_local.replace(month=dt_local.month + 1)
        else:
            return None
        
        next_dt_utc = next_dt.astimezone(pytz.UTC)
        return next_dt_utc.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M")
        
    except Exception as e:
        print(f"Ошибка при вычислении следующего времени: {e}")
        return None

def create_repeat_reminder(reminder_id):
    """Создает новое напоминание согласно типу повторения"""
    try:
        conn = get_db_connection()
        if not conn:
            return
        
        c = conn.cursor()
        c.execute("SELECT user_id, text, spam_interval, reminder_time, repeat_type, timezone FROM reminders WHERE id = ?", (reminder_id,))
        result = c.fetchone()
        
        if result:
            user_id, text, spam_interval, reminder_time, repeat_type, timezone = result
            
            next_time = get_next_reminder_time(reminder_time, repeat_type, timezone)
            
            if next_time:
                c.execute("""INSERT INTO reminders 
                             (user_id, reminder_time, text, spam_interval, last_spam_time, repeat_type, timezone) 
                             VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          (user_id, next_time, text, spam_interval, 
                           datetime.now().strftime("%Y-%m-%d %H:%M:%S"), repeat_type, timezone))
                
                c.execute("UPDATE reminders SET is_done = 1 WHERE id = ?", (reminder_id,))
                conn.commit()
                
                repeat_names = {
                    'daily': 'каждый день',
                    'weekly': 'каждую неделю',
                    'monthly': 'каждый месяц'
                }
                
                tz = pytz.timezone(timezone)
                dt_utc = datetime.strptime(next_time, "%Y-%m-%d %H:%M")
                dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
                dt_local = dt_utc.astimezone(tz)
                next_time_local = dt_local.strftime("%d.%m.%Y %H:%M")
                
                bot.send_message(
                    user_id,
                    f"🔄 **Напоминание продлено!**\n\n"
                    f"📝 Текст: {text}\n"
                    f"📅 Следующее: {next_time_local}\n"
                    f"📆 Тип повторения: {repeat_names.get(repeat_type, repeat_type)}\n"
                    f"⏱️ Интервал спама: {spam_interval // 60} минут\n\n"
                    f"_Когда наступит время, я снова начну спамить._",
                    parse_mode='Markdown',
                    reply_markup=get_main_keyboard()
                )
                
                print(f"🔄 Повтор для напоминания #{reminder_id} на {next_time}")
            else:
                print(f"⚠️ Не удалось вычислить следующее время для #{reminder_id}")
                conn.rollback()
        else:
            print(f"⚠️ Напоминание #{reminder_id} не найдено")
        
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка в create_repeat_reminder: {e}")

def spam_reminders():
    """Фоновый поток для отправки напоминаний"""
    print("🔄 Запущен поток спамера")
    while True:
        try:
            active_reminders = get_active_reminders()
            now = datetime.now()
            
            for rem_id, user_id, text, spam_interval, last_spam_time, repeat_type, timezone, reminder_time in active_reminders:
                # Проверяем подписку перед отправкой
                if not check_subscription(user_id):
                    # Если пользователь отписался, не отправляем напоминание
                    print(f"⚠️ Пользователь {user_id} отписался от канала, пропускаем напоминание")
                    continue
                
                if last_spam_time:
                    try:
                        last_spam = datetime.strptime(last_spam_time, "%Y-%m-%d %H:%M:%S")
                        seconds_since_last_spam = (now - last_spam).total_seconds()
                    except:
                        seconds_since_last_spam = spam_interval + 1
                else:
                    seconds_since_last_spam = spam_interval + 1
                
                if seconds_since_last_spam >= spam_interval:
                    try:
                        spam_text = f"🔔 **НАПОМИНАНИЕ!**\n\n{text}\n\n"
                        
                        repeat_names = {
                            'daily': '🔄 Ежедневное',
                            'weekly': '📅 Еженедельное',
                            'monthly': '📆 Ежемесячное',
                            'none': '❌ Одноразовое'
                        }
                        if repeat_type in repeat_names:
                            spam_text += f"{repeat_names[repeat_type]} напоминание.\n\n"
                        
                        spam_text += "_Чтобы остановить спам, нажми кнопку ниже._"
                        
                        bot.send_message(
                            user_id, 
                            spam_text, 
                            reply_markup=get_spam_keyboard(rem_id),
                            parse_mode='Markdown'
                        )
                        update_last_spam_time(rem_id)
                        print(f"💬 Спам для напоминания #{rem_id}: '{text}'")
                    except Exception as e:
                        print(f"❌ Ошибка при отправке спама: {e}")
            
            time.sleep(30)
        except Exception as e:
            print(f"❌ Ошибка в spam_reminders: {e}")
            time.sleep(60)

@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def handle_check_subscription(call):
    """Обработчик кнопки проверки подписки"""
    user_id = call.from_user.id
    
    # Очищаем кэш для этого пользователя
    if user_id in subscription_cache:
        del subscription_cache[user_id]
    
    if check_subscription(user_id):
        bot.answer_callback_query(call.id, "✅ Подписка подтверждена! Добро пожаловать!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(
            user_id,
            "✅ Отлично! Ты подписался на канал!\n\n"
            "👋 Привет! Я бот-напоминалка-спамер!\n\n"
            "Я помогу тебе не забыть о важных делах.\n"
            "Используй кнопки ниже для управления:",
            reply_markup=get_main_keyboard()
        )
    else:
        bot.answer_callback_query(
            call.id, 
            "❌ Ты еще не подписался! Подпишись и нажми 'Проверить подписку'.",
            show_alert=True
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("done_"))
def handle_done_button(call):
    reminder_id = int(call.data.split("_")[1])
    
    # Проверяем подписку перед обработкой
    if not check_subscription(call.from_user.id):
        bot.answer_callback_query(
            call.id, 
            "❌ Для использования бота подпишись на канал!",
            show_alert=True
        )
        return
    
    try:
        conn = get_db_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка базы данных")
            return
        
        c = conn.cursor()
        c.execute("SELECT text, repeat_type FROM reminders WHERE id = ? AND is_done = 0", (reminder_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            text, repeat_type = result
            
            if repeat_type != 'none':
                bot.answer_callback_query(call.id, "✅ Прочитано!")
                
                repeat_names = {
                    'daily': 'каждый день',
                    'weekly': 'каждую неделю',
                    'monthly': 'каждый месяц'
                }
                
                bot.edit_message_text(
                    f"✅ **ВЫПОЛНЕНО:** {text}\n\n"
                    f"🔄 Это {repeat_names.get(repeat_type, 'повторяющееся')} напоминание.\n"
                    f"Продолжить напоминать?",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
                bot.send_message(
                    call.message.chat.id,
                    "Что делаем с напоминанием?",
                    reply_markup=get_repeat_keyboard(reminder_id)
                )
            else:
                mark_reminder_done(reminder_id)
                bot.answer_callback_query(call.id, "✅ Отлично! Напоминание прочитано.")
                bot.edit_message_text(
                    f"✅ **ВЫПОЛНЕНО:** {text}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
                bot.send_message(
                    call.message.chat.id, 
                    "🎉 Спам остановлен! Молодец!",
                    reply_markup=get_main_keyboard()
                )
        else:
            bot.answer_callback_query(call.id, "⚠️ Напоминание уже выполнено")
    except Exception as e:
        print(f"❌ Ошибка в handle_done_button: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("repeat_"))
def handle_repeat_choice(call):
    # Проверяем подписку перед обработкой
    if not check_subscription(call.from_user.id):
        bot.answer_callback_query(
            call.id, 
            "❌ Для использования бота подпишись на канал!",
            show_alert=True
        )
        return
    
    try:
        action, choice, reminder_id = call.data.split("_")
        reminder_id = int(reminder_id)
        user_id = call.from_user.id
        
        if choice == "yes":
            bot.answer_callback_query(call.id, "🔄 Продолжаю!")
            bot.delete_message(call.message.chat.id, call.message.message_id)
            create_repeat_reminder(reminder_id)
            
        elif choice == "no":
            mark_reminder_done(reminder_id)
            bot.answer_callback_query(call.id, "⏹️ Повтор отключен!")
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                user_id,
                "✅ Повтор остановлен. Напоминание больше не будет приходить.",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        print(f"❌ Ошибка в handle_repeat_choice: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def handle_delete(call):
    user_id = call.from_user.id
    
    # Проверяем подписку перед обработкой
    if not check_subscription(user_id):
        bot.answer_callback_query(
            call.id, 
            "❌ Для использования бота подпишись на канал!",
            show_alert=True
        )
        return
    
    if call.data == "delete_cancel":
        bot.answer_callback_query(call.id, "Отмена")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(user_id, "❌ Удаление отменено.", reply_markup=get_main_keyboard())
        return
    
    reminder_id = int(call.data.split("_")[1])
    
    try:
        conn = get_db_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка базы данных")
            return
        
        c = conn.cursor()
        c.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
        conn.commit()
        rows_affected = c.rowcount
        conn.close()
        
        if rows_affected > 0:
            bot.answer_callback_query(call.id, "✅ Удалено!")
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(user_id, "🗑️ Напоминание удалено.", reply_markup=get_main_keyboard())
        else:
            bot.answer_callback_query(call.id, "⚠️ Ошибка")
    except Exception as e:
        print(f"❌ Ошибка в handle_delete: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка")

# ===== ОБРАБОТЧИКИ КНОПОК =====

@bot.message_handler(func=lambda message: message.text == "➕ Новая напоминалка")
def new_reminder_button(message):
    user_id = message.from_user.id
    
    # Проверяем подписку
    if not check_subscription(user_id):
        bot.send_message(
            user_id,
            "🔒 **Для использования бота нужно подписаться на канал!**\n\n"
            "Подпишись на наш канал, чтобы получать актуальные новости и обновления:\n"
            "👉 [VibeDev Веб-разработка](https://t.me/VibeDev_rus)\n\n"
            "После подписки нажми кнопку 'Проверить подписку'.",
            parse_mode='Markdown',
            reply_markup=get_subscribe_keyboard()
        )
        return
    
    if user_id in user_data:
        del user_data[user_id]
    user_data[user_id] = {}
    
    msg = bot.send_message(
        user_id,
        "🌍 **Шаг 1 из 5: Выберите ваш часовой пояс**\n\n"
        "Укажите ваш часовой пояс, чтобы я правильно определял время.\n"
        "Выберите из списка или напишите свой (например, UTC+4 или +4):",
        parse_mode='Markdown',
        reply_markup=get_timezone_keyboard()
    )
    bot.register_next_step_handler(msg, get_timezone)

@bot.message_handler(func=lambda message: message.text == "📋 Все напоминалки")
def list_reminders_button(message):
    user_id = message.from_user.id
    
    # Проверяем подписку
    if not check_subscription(user_id):
        bot.send_message(
            user_id,
            "🔒 **Для использования бота нужно подписаться на канал!**\n\n"
            "Подпишись на наш канал:\n"
            "👉 [VibeDev Веб-разработка](https://t.me/VibeDev_rus)\n\n"
            "После подписки нажми кнопку 'Проверить подписку'.",
            parse_mode='Markdown',
            reply_markup=get_subscribe_keyboard()
        )
        return
    
    try:
        conn = get_db_connection()
        if not conn:
            bot.send_message(user_id, "❌ Ошибка базы данных", reply_markup=get_main_keyboard())
            return
        
        c = conn.cursor()
        c.execute("SELECT id, reminder_time, text, spam_interval, repeat_type, timezone FROM reminders WHERE user_id = ? AND is_done = 0 ORDER BY reminder_time", (user_id,))
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            bot.send_message(
                user_id, 
                "📭 У тебя нет активных напоминаний.",
                reply_markup=get_main_keyboard()
            )
            return
        
        text = "📋 **Твои активные напоминания:**\n\n"
        for i, (rem_id, rem_time, rem_text, interval, repeat_type, timezone) in enumerate(rows, 1):
            minutes = interval // 60
            
            try:
                tz = pytz.timezone(timezone)
                dt_utc = datetime.strptime(rem_time, "%Y-%m-%d %H:%M")
                dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
                dt_local = dt_utc.astimezone(tz)
                rem_time_local = dt_local.strftime("%d.%m.%Y %H:%M")
            except:
                rem_time_local = rem_time
            
            repeat_names = {
                'daily': '🔄 Ежедневно',
                'weekly': '📅 Еженедельно',
                'monthly': '📆 Ежемесячно',
                'none': '❌ Одноразовое'
            }
            repeat_text = repeat_names.get(repeat_type, '❌ Одноразовое')
            
            text += f"{i}. 📝 {rem_text}\n"
            text += f"   📅 {rem_time_local}\n"
            text += f"   ⏱️ Каждые {minutes} мин\n"
            text += f"   {repeat_text}\n\n"
        
        bot.send_message(
            user_id, 
            text, 
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        print(f"❌ Ошибка в list_reminders_button: {e}")
        bot.send_message(user_id, "❌ Произошла ошибка при получении списка", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "🗑️ Удалить напоминалку")
def delete_reminder_button(message):
    user_id = message.from_user.id
    
    # Проверяем подписку
    if not check_subscription(user_id):
        bot.send_message(
            user_id,
            "🔒 **Для использования бота нужно подписаться на канал!**\n\n"
            "Подпишись на наш канал:\n"
            "👉 [VibeDev Веб-разработка](https://t.me/VibeDev_rus)\n\n"
            "После подписки нажми кнопку 'Проверить подписку'.",
            parse_mode='Markdown',
            reply_markup=get_subscribe_keyboard()
        )
        return
    
    try:
        conn = get_db_connection()
        if not conn:
            bot.send_message(user_id, "❌ Ошибка базы данных", reply_markup=get_main_keyboard())
            return
        
        c = conn.cursor()
        c.execute("SELECT id, reminder_time, text, timezone FROM reminders WHERE user_id = ? AND is_done = 0", (user_id,))
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            bot.send_message(
                user_id, 
                "📭 У тебя нет активных напоминаний для удаления.",
                reply_markup=get_main_keyboard()
            )
            return
        
        keyboard = InlineKeyboardMarkup(row_width=1)
        for rem_id, rem_time, rem_text, timezone in rows:
            try:
                tz = pytz.timezone(timezone)
                dt_utc = datetime.strptime(rem_time, "%Y-%m-%d %H:%M")
                dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
                dt_local = dt_utc.astimezone(tz)
                rem_time_local = dt_local.strftime("%d.%m %H:%M")
            except:
                rem_time_local = rem_time
            
            button_text = f"🗑️ {rem_text[:20]} ({rem_time_local})"
            keyboard.add(InlineKeyboardButton(button_text, callback_data=f"delete_{rem_id}"))
        
        keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="delete_cancel"))
        
        bot.send_message(
            user_id,
            "Выбери напоминание для удаления:",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"❌ Ошибка в delete_reminder_button: {e}")
        bot.send_message(user_id, "❌ Произошла ошибка", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "❌ Отменить создание")
def cancel_creation_button(message):
    user_id = message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    bot.send_message(
        user_id,
        "❌ Создание напоминания отменено.",
        reply_markup=get_main_keyboard()
    )

# ===== ОСНОВНЫЕ ОБРАБОТЧИКИ =====

def get_timezone(message):
    user_id = message.from_user.id
    
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    tz_text = message.text.strip()
    
    tz_found = parse_timezone(tz_text)
    
    if not tz_found:
        tz_found = 'Europe/Moscow'
        bot.send_message(
            user_id,
            f"❌ Не понял часовой пояс. Использую МСК (UTC+3) по умолчанию.",
            reply_markup=telebot.types.ReplyKeyboardRemove()
        )
    else:
        bot.send_message(
            user_id,
            f"✅ Часовой пояс установлен! ({tz_found})",
            reply_markup=telebot.types.ReplyKeyboardRemove()
        )
    
    user_data[user_id]['timezone'] = tz_found
    
    msg = bot.send_message(
        user_id,
        "📝 **Шаг 2 из 5: Введите название напоминания**\n\n"
        "Например: *Купить молоко* или *Позвонить маме*\n\n"
        "Или нажмите кнопку ниже, чтобы отменить создание:",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    bot.register_next_step_handler(msg, get_reminder_text)

def get_reminder_text(message):
    user_id = message.from_user.id
    
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    reminder_text = message.text.strip()
    
    if len(reminder_text) < 1:
        msg = bot.send_message(
            user_id, 
            "❌ Название не может быть пустым. Попробуй еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, get_reminder_text)
        return
    
    user_data[user_id]['text'] = reminder_text
    
    msg = bot.send_message(
        user_id,
        "📅 **Шаг 3 из 5: Введите дату и время**\n\n"
        "В формате: `ДД ММ ГГ ЧЧ ММ`\n"
        "Например: `03 07 26 15 30` (3 июля 2026, 15:30)\n\n"
        "⚠️ Время должно быть в будущем!\n\n"
        "Или нажмите кнопку ниже, чтобы отменить создание:",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    bot.register_next_step_handler(msg, get_reminder_datetime)

def get_reminder_datetime(message):
    user_id = message.from_user.id
    
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    datetime_text = message.text.strip()
    timezone = user_data[user_id].get('timezone', 'Europe/Moscow')
    
    dt_utc, error = parse_custom_datetime(datetime_text, timezone)
    
    if error:
        msg = bot.send_message(
            user_id,
            f"❌ {error}\n\n"
            "Попробуй еще раз в формате:\n"
            "`ДД ММ ГГ ЧЧ ММ`\n"
            "Например: `03 07 26 15 30`",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, get_reminder_datetime)
        return
    
    if not dt_utc:
        msg = bot.send_message(
            user_id,
            "❌ Неверный формат!\n\n"
            "Используй: `ДД ММ ГГ ЧЧ ММ`\n"
            "Например: `03 07 26 15 30`",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, get_reminder_datetime)
        return
    
    now_utc = datetime.now(pytz.UTC).replace(tzinfo=None)
    if dt_utc <= now_utc:
        msg = bot.send_message(
            user_id,
            "❌ Нельзя установить напоминание в прошлом!\n\n"
            "Введите дату и время в будущем:\n"
            "`ДД ММ ГГ ЧЧ ММ`\n"
            "Например: `03 07 26 15 30`",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, get_reminder_datetime)
        return
    
    user_data[user_id]['datetime_utc'] = dt_utc.strftime("%Y-%m-%d %H:%M")
    
    tz = pytz.timezone(timezone)
    dt_local = dt_utc.replace(tzinfo=pytz.UTC).astimezone(tz)
    dt_local_str = dt_local.strftime("%d.%m.%Y %H:%M")
    
    bot.send_message(
        user_id,
        f"✅ Время сохранено!\n"
        f"📅 Ваше время: {dt_local_str}\n"
        f"🌍 Часовой пояс: {timezone}"
    )
    
    msg = bot.send_message(
        user_id,
        "⏱️ **Шаг 4 из 5: Выберите интервал спама**\n\n"
        "Как часто я должен напоминать тебе?\n"
        "Выбери вариант ниже или напиши число в минутах:",
        parse_mode='Markdown',
        reply_markup=get_interval_keyboard()
    )
    bot.register_next_step_handler(msg, get_spam_interval)

def get_spam_interval(message):
    user_id = message.from_user.id
    
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    interval_text = message.text.strip().lower()
    
    interval_map = {
        '1 минута': 60,
        '1 мин': 60,
        '5 минут': 300,
        '5 мин': 300,
        '10 минут': 600,
        '10 мин': 600,
        '30 минут': 1800,
        '30 мин': 1800,
        '1 час': 3600,
        '60 мин': 3600
    }
    
    if interval_text in interval_map:
        spam_interval = interval_map[interval_text]
    else:
        try:
            minutes = int(interval_text)
            if minutes < 1:
                minutes = 1
            spam_interval = minutes * 60
        except ValueError:
            bot.send_message(
                user_id,
                "❌ Не понял интервал. Используй кнопки или напиши число в минутах.\n\n"
                "Попробуй еще раз:",
                reply_markup=get_interval_keyboard()
            )
            bot.register_next_step_handler(message, get_spam_interval)
            return
    
    user_data[user_id]['interval'] = spam_interval
    
    bot.send_message(
        user_id,
        "✅ Отлично!",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    
    msg = bot.send_message(
        user_id,
        "🔄 **Шаг 5 из 5: Выберите тип повторения**\n\n"
        "Как часто нужно повторять это напоминание?\n\n"
        "• 📆 **Каждый месяц** - в это же число, в это же время\n"
        "• 📅 **Каждую неделю** - в этот же день недели, в это же время\n"
        "• 🔄 **Каждый день** - каждый день в это же время\n"
        "• ❌ **Не повторять** - только один раз",
        parse_mode='Markdown',
        reply_markup=get_repeat_type_keyboard()
    )
    bot.register_next_step_handler(msg, get_repeat_type)

def get_repeat_type(message):
    user_id = message.from_user.id
    
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    choice = message.text.strip().lower()
    
    repeat_type = 'none'
    repeat_name = ''
    
    if 'месяц' in choice or 'ежемесяч' in choice:
        repeat_type = 'monthly'
        repeat_name = 'каждый месяц'
    elif 'недел' in choice or 'еженедел' in choice:
        repeat_type = 'weekly'
        repeat_name = 'каждую неделю'
    elif 'день' in choice or 'ежеднев' in choice:
        repeat_type = 'daily'
        repeat_name = 'каждый день'
    elif 'не повтор' in choice or 'один раз' in choice or 'нет' in choice:
        repeat_type = 'none'
        repeat_name = 'не повторять'
    else:
        bot.send_message(
            user_id,
            "❌ Не понял. Выбери один из вариантов:",
            reply_markup=get_repeat_type_keyboard()
        )
        bot.register_next_step_handler(message, get_repeat_type)
        return
    
    bot.send_message(
        user_id,
        f"✅ Выбрано: {repeat_name}",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    
    success = add_reminder(
        user_id,
        user_data[user_id]['datetime_utc'],
        user_data[user_id]['text'],
        user_data[user_id]['interval'],
        repeat_type,
        user_data[user_id]['timezone']
    )
    
    if not success:
        bot.send_message(
            user_id,
            "❌ Произошла ошибка при сохранении напоминания. Попробуйте еще раз.",
            reply_markup=get_main_keyboard()
        )
        if user_id in user_data:
            del user_data[user_id]
        return
    
    minutes = user_data[user_id]['interval'] // 60
    
    tz = pytz.timezone(user_data[user_id]['timezone'])
    dt_utc = datetime.strptime(user_data[user_id]['datetime_utc'], "%Y-%m-%d %H:%M")
    dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
    dt_local = dt_utc.astimezone(tz)
    dt_local_str = dt_local.strftime("%d.%m.%Y %H:%M")
    
    repeat_names = {
        'daily': '🔄 Каждый день',
        'weekly': '📅 Каждую неделю',
        'monthly': '📆 Каждый месяц',
        'none': '❌ Не повторять'
    }
    
    bot.send_message(
        user_id,
        f"✅ **Напоминание создано!**\n\n"
        f"📝 Текст: {user_data[user_id]['text']}\n"
        f"📅 Дата и время: `{dt_local_str}`\n"
        f"⏱️ Интервал спама: {minutes} минут(ы)\n"
        f"🔄 Повторение: {repeat_names.get(repeat_type, 'Не повторять')}\n"
        f"🌍 Часовой пояс: {user_data[user_id]['timezone']}\n\n"
        f"В назначенное время я начну спамить тебе, пока ты не нажмешь кнопку '✅ Прочитано'.",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )
    
    del user_data[user_id]

# ===== ОБРАБОТЧИК КОМАНДЫ /START =====

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    if not init_db():
        bot.send_message(
            user_id,
            "❌ Ошибка инициализации базы данных. Попробуйте перезапустить бота.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Проверяем подписку
    if check_subscription(user_id):
        bot.send_message(
            user_id,
            "👋 Привет! Я бот-напоминалка-спамер!\n\n"
            "Я помогу тебе не забыть о важных делах.\n"
            "Используй кнопки ниже для управления:",
            reply_markup=get_main_keyboard()
        )
    else:
        bot.send_message(
            user_id,
            "🔒 **Для использования бота нужно подписаться на канал!**\n\n"
            "Подпишись на наш канал, чтобы получать актуальные новости и обновления:\n"
            "👉 [VibeDev Веб-разработка](https://t.me/VibeDev_rus)\n\n"
            "После подписки нажми кнопку 'Проверить подписку'.",
            parse_mode='Markdown',
            reply_markup=get_subscribe_keyboard()
        )

# ===== ЗАПУСК =====

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    
    if not init_db():
        print("❌ Ошибка инициализации БД! Бот не может работать.")
        exit(1)
    
    spam_thread = threading.Thread(target=spam_reminders, daemon=True)
    spam_thread.start()
    
    print("🤖 Бот-спамер запущен!")
    print("📝 Бот с проверкой подписки на канал!")
    print(f"📢 Канал: {CHANNEL_ID}")
    print("Ожидание сообщений...")
    
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ Ошибка при работе бота: {e}")