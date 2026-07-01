import os
import sys
import subprocess
import threading
import time
import requests
from flask import Flask, request
from datetime import datetime, timedelta
import re
import pytz
import sqlite3

# ====================================================
# 1. ПРОВЕРКА И УСТАНОВКА ЗАВИСИМОСТЕЙ
# ====================================================
# Этот блок проверяет, установлены ли все библиотеки.
# Если нет — устанавливает их автоматически.
# ====================================================
print("📦 Проверяю установку зависимостей...")
try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
    print("✅ telebot уже установлен")
except ImportError:
    print("⚠️ telebot не найден, устанавливаю...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("✅ Зависимости установлены!")

# Теперь импортируем всё
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ====================================================
# 2. БЕЗОПАСНОЕ ЧТЕНИЕ ТОКЕНА
# ====================================================
# ЭТА ЧАСТЬ ПЫТАЕТСЯ НАЙТИ ТОКЕН В НЕСКОЛЬКИХ МЕСТАХ:
# 1. Сначала проверяет переменные окружения (os.environ)
# 2. Потом ищет в секретных файлах Render (/etc/secrets/)
# 3. Удаляет все пробелы и лишние символы
# ====================================================

TELEGRAM_TOKEN = None

# 1. Пробуем из переменной окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if TELEGRAM_TOKEN:
    print("✅ Токен найден в переменной окружения")

# 2. Если не нашли — ищем в секретных файлах
if not TELEGRAM_TOKEN:
    secret_paths = [
        '/etc/secrets/.env',
        '/etc/secrets/token.txt',
        '/etc/secrets/TOKEN'
    ]
    for path in secret_paths:
        try:
            with open(path, 'r') as f:
                content = f.read()
                # Ищем строку с TELEGRAM_TOKEN
                for line in content.split('\n'):
                    if 'TELEGRAM_TOKEN' in line:
                        if '=' in line:
                            TELEGRAM_TOKEN = line.split('=', 1)[1]
                        else:
                            TELEGRAM_TOKEN = line
                        break
                if TELEGRAM_TOKEN:
                    print(f"✅ Токен найден в {path}")
                    break
        except Exception as e:
            print(f"⚠️ Не удалось прочитать {path}: {e}")

# 3. Очищаем от пробелов, переносов и кавычек
if TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = ''.join(TELEGRAM_TOKEN.split())  # Удаляем все пробелы
    TELEGRAM_TOKEN = TELEGRAM_TOKEN.strip('"\'')      # Удаляем кавычки
    print(f"✅ Токен загружен: {TELEGRAM_TOKEN[:10]}...")

# 4. Если токен не найден — завершаем работу
if not TELEGRAM_TOKEN:
    print("❌ ТОКЕН НЕ НАЙДЕН!")
    print("Создай Secret File с именем '.env' и содержимым:")
    print("TELEGRAM_TOKEN=твой_токен")
    raise RuntimeError("TELEGRAM_TOKEN не найден")

# ====================================================
# 3. ЧТЕНИЕ CHANNEL_ID
# ====================================================
CHANNEL_ID = os.environ.get('CHANNEL_ID')
if not CHANNEL_ID:
    try:
        with open('/etc/secrets/.env', 'r') as f:
            for line in f:
                if 'CHANNEL_ID' in line:
                    CHANNEL_ID = line.split('=')[1].strip().replace(' ', '')
                    break
    except:
        pass

if not CHANNEL_ID:
    CHANNEL_ID = '@VibeDev_rus'

print(f"📢 Канал: {CHANNEL_ID}")

# ====================================================
# 4. НАСТРОЙКИ БАЗЫ ДАННЫХ
# ====================================================
DB_NAME = "reminders.db"

# ====================================================
# 5. СОЗДАЁМ БОТА
# ====================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ====================================================
# 6. ФУНКЦИИ БАЗЫ ДАННЫХ
# ====================================================
def init_db():
    """Создаёт таблицу в базе данных, если её нет"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS reminders (
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
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
        return True
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return False

def add_reminder(user_id, reminder_time, text, spam_interval, repeat_type, timezone):
    """Добавляет новое напоминание в базу данных"""
    try:
        conn = sqlite3.connect(DB_NAME)
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
        print(f"❌ Ошибка добавления: {e}")
        return False

def get_active_reminders():
    """Получает все активные (не выполненные) напоминания, время которых уже наступило"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("""SELECT id, user_id, text, spam_interval, last_spam_time, repeat_type, timezone, reminder_time
                     FROM reminders WHERE reminder_time <= ? AND is_done = 0""", (now,))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ Ошибка получения: {e}")
        return []

def mark_reminder_done(reminder_id):
    """Отмечает напоминание как выполненное"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("UPDATE reminders SET is_done = 1 WHERE id = ?", (reminder_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def update_last_spam_time(reminder_id):
    """Обновляет время последнего отправленного спама"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE reminders SET last_spam_time = ? WHERE id = ?", (now, reminder_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def get_user_reminders(user_id):
    """Получает все активные напоминания пользователя"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, reminder_time, text, spam_interval, repeat_type, timezone FROM reminders WHERE user_id = ? AND is_done = 0", (user_id,))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []

def delete_reminder(reminder_id, user_id):
    """Удаляет напоминание"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

# ====================================================
# 7. ЧАСОВЫЕ ПОЯСА
# ====================================================
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

def parse_timezone(tz_text):
    """Парсит текстовое представление часового пояса"""
    tz_text = tz_text.strip().upper()
    
    # Проверяем по словарю
    for key, value in TIMEZONES.items():
        if key in tz_text:
            return value
    
    # Проверяем UTC+XX или UTC-XX
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
    
    # Проверяем просто +4 или -4
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
    """Парсит дату в формате 'ДД ММ ГГ ЧЧ ММ'"""
    try:
        parts = date_str.strip().split()
        if len(parts) != 5:
            return None, "Нужно: ДД ММ ГГ ЧЧ ММ"
        
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
    except Exception as e:
        return None, f"Ошибка: {e}"

# ====================================================
# 8. КЛАВИАТУРЫ
# ====================================================
def get_main_keyboard():
    """Главное меню с 4 кнопками"""
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
    keyboard.add(InlineKeyboardButton("📢 Подписаться на канал", url="https://t.me/VibeDev_rus"))
    keyboard.add(InlineKeyboardButton("✅ Проверить подписку", callback_data="check_subscription"))
    return keyboard

def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add(KeyboardButton("❌ Отменить создание"))
    return keyboard

def get_timezone_keyboard():
    """Клавиатура выбора часового пояса"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    keyboard.add(KeyboardButton("МСК (UTC+3)"), KeyboardButton("ЕКБ (UTC+5)"), KeyboardButton("НСК (UTC+7)"))
    keyboard.add(KeyboardButton("КРАС (UTC+7)"), KeyboardButton("ИРК (UTC+8)"), KeyboardButton("ВЛД (UTC+10)"))
    keyboard.add(KeyboardButton("КАМ (UTC+12)"), KeyboardButton("КИЕВ (UTC+2)"), KeyboardButton("МИНСК (UTC+3)"))
    keyboard.add(KeyboardButton("❌ Отменить создание"))
    return keyboard

def get_interval_keyboard():
    """Клавиатура выбора интервала спама"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=3)
    keyboard.add(KeyboardButton("1 минута"), KeyboardButton("5 минут"), KeyboardButton("10 минут"))
    keyboard.add(KeyboardButton("30 минут"), KeyboardButton("1 час"), KeyboardButton("❌ Отменить создание"))
    return keyboard

def get_repeat_type_keyboard():
    """Клавиатура выбора типа повторения"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    keyboard.add(KeyboardButton("📆 Каждый месяц"), KeyboardButton("📅 Каждую неделю"))
    keyboard.add(KeyboardButton("🔄 Каждый день"), KeyboardButton("❌ Не повторять"))
    keyboard.add(KeyboardButton("❌ Отменить создание"))
    return keyboard

def get_spam_keyboard(reminder_id):
    """Клавиатура с кнопкой 'Прочитано' для спам-сообщений"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ Прочитано", callback_data=f"done_{reminder_id}"))
    return keyboard

def get_repeat_keyboard(reminder_id):
    """Клавиатура выбора продолжения повторения"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔄 Продолжить", callback_data=f"repeat_yes_{reminder_id}"),
        InlineKeyboardButton("⏹️ Остановить", callback_data=f"repeat_no_{reminder_id}")
    )
    return keyboard

# ====================================================
# 9. ПРОВЕРКА ПОДПИСКИ
# ====================================================
subscription_cache = {}

def check_subscription(user_id):
    """Проверяет, подписан ли пользователь на канал"""
    try:
        current_time = time.time()
        if user_id in subscription_cache:
            cached_status, cached_time = subscription_cache[user_id]
            if current_time - cached_time < 10:  # Кэш на 10 секунд
                return cached_status
        
        try:
            status = bot.get_chat_member(CHANNEL_ID, user_id).status
            is_subscribed = status in ['member', 'administrator', 'creator']
        except:
            is_subscribed = True  # Если не можем проверить — даём доступ
        
        subscription_cache[user_id] = (is_subscribed, current_time)
        return is_subscribed
    except:
        return True

# ====================================================
# 10. ОБРАБОТЧИКИ СООБЩЕНИЙ
# ====================================================
user_data = {}

@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    init_db()
    
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
            "Подпишись на наш канал:\n"
            f"👉 {CHANNEL_ID}\n\n"
            "После подписки нажми кнопку 'Проверить подписку'.",
            parse_mode='Markdown',
            reply_markup=get_subscribe_keyboard()
        )

@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def handle_check_subscription(call):
    """Обработчик кнопки 'Проверить подписку'"""
    user_id = call.from_user.id
    if user_id in subscription_cache:
        del subscription_cache[user_id]
    
    if check_subscription(user_id):
        bot.answer_callback_query(call.id, "✅ Подписка подтверждена!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(
            user_id,
            "✅ Отлично! Ты подписался на канал!\n\n"
            "👋 Привет! Я бот-напоминалка-спамер!\n\n"
            "Используй кнопки ниже:",
            reply_markup=get_main_keyboard()
        )
    else:
        bot.answer_callback_query(
            call.id,
            "❌ Ты еще не подписался! Подпишись и нажми 'Проверить подписку'.",
            show_alert=True
        )

@bot.message_handler(func=lambda message: message.text == "➕ Новая напоминалка")
def new_reminder_button(message):
    """Обработчик кнопки 'Новая напоминалка'"""
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.send_message(
            user_id,
            "🔒 **Подпишись на канал!**\n"
            f"👉 {CHANNEL_ID}",
            parse_mode='Markdown',
            reply_markup=get_subscribe_keyboard()
        )
        return
    
    if user_id in user_data:
        del user_data[user_id]
    user_data[user_id] = {}
    
    msg = bot.send_message(
        user_id,
        "🌍 **Шаг 1 из 5: Выберите часовой пояс**\n\n"
        "Укажите ваш часовой пояс, чтобы я правильно определял время.\n"
        "Выберите из списка или напишите свой (например, UTC+4 или +4):",
        parse_mode='Markdown',
        reply_markup=get_timezone_keyboard()
    )
    bot.register_next_step_handler(msg, get_timezone)

def get_timezone(message):
    """Шаг 1: Получение часового пояса"""
    user_id = message.from_user.id
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    tz_found = parse_timezone(message.text)
    if not tz_found:
        tz_found = 'Europe/Moscow'
        bot.send_message(user_id, "❌ Не понял часовой пояс. Использую МСК (UTC+3) по умолчанию.")
    else:
        bot.send_message(user_id, f"✅ Часовой пояс установлен: {tz_found}")
    
    user_data[user_id]['timezone'] = tz_found
    msg = bot.send_message(
        user_id,
        "📝 **Шаг 2 из 5: Введите название напоминания**\n\n"
        "Например: *Купить молоко* или *Позвонить маме*",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    bot.register_next_step_handler(msg, get_reminder_text)

def get_reminder_text(message):
    """Шаг 2: Получение названия напоминания"""
    user_id = message.from_user.id
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    if len(message.text.strip()) < 1:
        msg = bot.send_message(user_id, "❌ Название не может быть пустым. Попробуй еще раз:", reply_markup=get_cancel_keyboard())
        bot.register_next_step_handler(msg, get_reminder_text)
        return
    
    user_data[user_id]['text'] = message.text.strip()
    msg = bot.send_message(
        user_id,
        "📅 **Шаг 3 из 5: Введите дату и время**\n\n"
        "В формате: `ДД ММ ГГ ЧЧ ММ`\n"
        "Например: `03 07 26 15 30` (3 июля 2026, 15:30)\n\n"
        "⚠️ Время должно быть в будущем!",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    bot.register_next_step_handler(msg, get_reminder_datetime)

def get_reminder_datetime(message):
    """Шаг 3: Получение даты и времени"""
    user_id = message.from_user.id
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    timezone = user_data[user_id].get('timezone', 'Europe/Moscow')
    dt_utc, error = parse_custom_datetime(message.text, timezone)
    
    if error:
        msg = bot.send_message(
            user_id,
            f"❌ {error}\n\nПопробуй еще раз в формате:\n`ДД ММ ГГ ЧЧ ММ`",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, get_reminder_datetime)
        return
    
    now_utc = datetime.now(pytz.UTC).replace(tzinfo=None)
    if dt_utc <= now_utc:
        msg = bot.send_message(
            user_id,
            "❌ Нельзя установить напоминание в прошлом!\n\nВведите дату и время в будущем:",
            reply_markup=get_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, get_reminder_datetime)
        return
    
    user_data[user_id]['datetime_utc'] = dt_utc.strftime("%Y-%m-%d %H:%M")
    
    tz = pytz.timezone(timezone)
    dt_local = dt_utc.replace(tzinfo=pytz.UTC).astimezone(tz)
    bot.send_message(
        user_id,
        f"✅ Время сохранено!\n"
        f"📅 Ваше время: {dt_local.strftime('%d.%m.%Y %H:%M')}"
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
    """Шаг 4: Получение интервала спама"""
    user_id = message.from_user.id
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    interval_map = {
        '1 минута': 60, '5 минут': 300, '10 минут': 600,
        '30 минут': 1800, '1 час': 3600
    }
    interval_text = message.text.strip().lower()
    
    if interval_text in interval_map:
        spam_interval = interval_map[interval_text]
    else:
        try:
            minutes = int(interval_text)
            spam_interval = max(60, minutes * 60)
        except:
            bot.send_message(
                user_id,
                "❌ Не понял интервал. Используй кнопки или напиши число в минутах.\n\nПопробуй еще раз:",
                reply_markup=get_interval_keyboard()
            )
            bot.register_next_step_handler(message, get_spam_interval)
            return
    
    user_data[user_id]['interval'] = spam_interval
    bot.send_message(user_id, "✅ Отлично!", reply_markup=telebot.types.ReplyKeyboardRemove())
    
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
    """Шаг 5: Получение типа повторения"""
    user_id = message.from_user.id
    if message.text == "❌ Отменить создание":
        if user_id in user_data:
            del user_data[user_id]
        bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())
        return
    
    choice = message.text.strip().lower()
    repeat_type = 'none'
    repeat_name = 'не повторять'
    
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
    
    bot.send_message(user_id, f"✅ Выбрано: {repeat_name}", reply_markup=telebot.types.ReplyKeyboardRemove())
    
    add_reminder(
        user_id,
        user_data[user_id]['datetime_utc'],
        user_data[user_id]['text'],
        user_data[user_id]['interval'],
        repeat_type,
        user_data[user_id]['timezone']
    )
    
    minutes = user_data[user_id]['interval'] // 60
    tz = pytz.timezone(user_data[user_id]['timezone'])
    dt_utc = datetime.strptime(user_data[user_id]['datetime_utc'], "%Y-%m-%d %H:%M")
    dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
    dt_local = dt_utc.astimezone(tz)
    
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
        f"📅 Дата и время: `{dt_local.strftime('%d.%m.%Y %H:%M')}`\n"
        f"⏱️ Интервал спама: {minutes} минут(ы)\n"
        f"🔄 Повторение: {repeat_names.get(repeat_type, '❌ Не повторять')}\n"
        f"🌍 Часовой пояс: {user_data[user_id]['timezone']}\n\n"
        f"В назначенное время я начну спамить тебе, пока ты не нажмешь кнопку '✅ Прочитано'.",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )
    
    del user_data[user_id]

@bot.message_handler(func=lambda message: message.text == "📋 Все напоминалки")
def list_reminders(message):
    """Обработчик кнопки 'Все напоминалки'"""
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.send_message(user_id, "🔒 Подпишись на канал!", reply_markup=get_subscribe_keyboard())
        return
    
    rows = get_user_reminders(user_id)
    
    if not rows:
        bot.send_message(user_id, "📭 У тебя нет активных напоминаний.", reply_markup=get_main_keyboard())
        return
    
    text = "📋 **Твои активные напоминания:**\n\n"
    for i, (rem_id, rem_time, rem_text, interval, repeat_type, timezone) in enumerate(rows, 1):
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
        text += f"{i}. 📝 {rem_text}\n"
        text += f"   📅 {rem_time_local}\n"
        text += f"   ⏱️ Каждые {interval//60} мин\n"
        text += f"   {repeat_names.get(repeat_type, '❌ Одноразовое')}\n\n"
    
    bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "🗑️ Удалить напоминалку")
def delete_reminder_button(message):
    """Обработчик кнопки 'Удалить напоминалку'"""
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.send_message(user_id, "🔒 Подпишись на канал!", reply_markup=get_subscribe_keyboard())
        return
    
    rows = get_user_reminders(user_id)
    
    if not rows:
        bot.send_message(user_id, "📭 Нет напоминаний для удаления.", reply_markup=get_main_keyboard())
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for rem_id, rem_time, rem_text, interval, repeat_type, timezone in rows:
        try:
            tz = pytz.timezone(timezone)
            dt_utc = datetime.strptime(rem_time, "%Y-%m-%d %H:%M")
            dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
            dt_local = dt_utc.astimezone(tz)
            rem_time_local = dt_local.strftime("%d.%m %H:%M")
        except:
            rem_time_local = rem_time
        
        keyboard.add(InlineKeyboardButton(
            f"🗑️ {rem_text[:20]} ({rem_time_local})",
            callback_data=f"delete_{rem_id}"
        ))
    
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="delete_cancel"))
    bot.send_message(user_id, "Выбери напоминание для удаления:", reply_markup=keyboard)

@bot.message_handler(func=lambda message: message.text == "❌ Отменить создание")
def cancel_creation(message):
    """Обработчик кнопки 'Отменить создание'"""
    user_id = message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    bot.send_message(user_id, "❌ Создание отменено.", reply_markup=get_main_keyboard())

# ====================================================
# 11. CALLBACK ОБРАБОТЧИКИ
# ====================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("done_"))
def handle_done(call):
    """Обработчик кнопки 'Прочитано' в спам-сообщениях"""
    reminder_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    
    if not check_subscription(user_id):
        bot.answer_callback_query(call.id, "❌ Подпишись на канал!", show_alert=True)
        return
    
    conn = sqlite3.connect(DB_NAME)
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
            bot.answer_callback_query(call.id, "✅ Отлично!")
            bot.edit_message_text(
                f"✅ **ВЫПОЛНЕНО:** {text}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='Markdown'
            )
            bot.send_message(call.message.chat.id, "🎉 Спам остановлен! Молодец!", reply_markup=get_main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("repeat_"))
def handle_repeat(call):
    """Обработчик кнопок 'Продолжить' и 'Остановить' для повторяющихся напоминаний"""
    action, choice, reminder_id = call.data.split("_")
    reminder_id = int(reminder_id)
    user_id = call.from_user.id
    
    if choice == "yes":
        bot.answer_callback_query(call.id, "🔄 Продолжаю!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT user_id, text, spam_interval, reminder_time, repeat_type, timezone FROM reminders WHERE id = ?", (reminder_id,))
        result = c.fetchone()
        
        if result:
            user_id, text, spam_interval, reminder_time, repeat_type, timezone = result
            tz = pytz.timezone(timezone)
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
                conn.close()
                return
            
            next_dt_utc = next_dt.astimezone(pytz.UTC)
            next_time = next_dt_utc.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M")
            
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
            
            bot.send_message(
                user_id,
                f"🔄 **Напоминание продлено!**\n\n"
                f"📝 Текст: {text}\n"
                f"📅 Следующее: {next_dt.strftime('%d.%m.%Y %H:%M')}\n"
                f"📆 Тип повторения: {repeat_names.get(repeat_type, repeat_type)}\n"
                f"⏱️ Интервал спама: {spam_interval // 60} минут",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
        conn.close()
    else:
        mark_reminder_done(reminder_id)
        bot.answer_callback_query(call.id, "⏹️ Повтор остановлен!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(user_id, "✅ Повтор остановлен. Напоминание больше не будет приходить.", reply_markup=get_main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def handle_delete_callback(call):
    """Обработчик кнопок удаления напоминаний"""
    user_id = call.from_user.id
    
    if call.data == "delete_cancel":
        bot.answer_callback_query(call.id, "Отмена")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(user_id, "❌ Удаление отменено.", reply_markup=get_main_keyboard())
        return
    
    reminder_id = int(call.data.split("_")[1])
    
    if delete_reminder(reminder_id, user_id):
        bot.answer_callback_query(call.id, "✅ Удалено!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(user_id, "🗑️ Напоминание удалено.", reply_markup=get_main_keyboard())
    else:
        bot.answer_callback_query(call.id, "⚠️ Ошибка при удалении")

# ====================================================
# 12. ФОНОВЫЙ ПОТОК ДЛЯ СПАМА
# ====================================================
def spam_reminders():
    """Фоновый поток, который проверяет напоминания и отправляет спам"""
    print("🔄 Запущен поток спамера")
    while True:
        try:
            active_reminders = get_active_reminders()
            now = datetime.now()
            
            for rem_id, user_id, text, spam_interval, last_spam_time, repeat_type, timezone, reminder_time in active_reminders:
                if not check_subscription(user_id):
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
            
            time.sleep(30)  # Проверка каждые 30 секунд
        except Exception as e:
            print(f"❌ Ошибка в spam_reminders: {e}")
            time.sleep(60)

# ====================================================
# 13. FLASK-СЕРВЕР
# ====================================================
app = Flask(__name__)

@app.route('/')
def index():
    """Главная страница для проверки работы бота"""
    return "🤖 Бот-напоминалка работает!"

@app.route('/health')
def health():
    """Страница для проверки здоровья (используется UptimeRobot)"""
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик вебхука от Telegram"""
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
        return "ERROR", 500

# ====================================================
# 14. ЗАПУСК
# ====================================================
if __name__ == '__main__':
    print("✅ Все настройки загружены!")
    
    # Инициализируем базу данных
    init_db()
    
    # Запускаем поток спамера
    spam_thread = threading.Thread(target=spam_reminders, daemon=True)
    spam_thread.start()
    
    # Настраиваем вебхук
    try:
        webhook_url = "https://tgbotnotify.onrender.com/webhook"
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
        response = requests.get(url)
        print(f"✅ Вебхук: {response.json()}")
    except Exception as e:
        print(f"⚠️ Ошибка настройки вебхука: {e}")
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Запускаю Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
