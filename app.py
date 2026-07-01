import os
import sys
import threading
from flask import Flask, request

# ====================================================
# ГЛАВНЫЙ ФАЙЛ ДЛЯ RENDER.COM
# ====================================================

# ПЫТАЕМСЯ ПРОЧИТАТЬ ТОКЕН ИЗ РАЗНЫХ ИСТОЧНИКОВ
TELEGRAM_TOKEN = None

# 1. Проверяем переменные окружения (обычные)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

# 2. Если не нашли, ищем в секретных файлах Render
if not TELEGRAM_TOKEN:
    secret_paths = [
        '/etc/secrets/token.txt',
        '/etc/secrets/TOKEN',
        '/etc/secrets/.env'
    ]
    for path in secret_paths:
        try:
            with open(path, 'r') as f:
                TELEGRAM_TOKEN = f.read().strip()
                print(f"✅ Токен найден в {path}")
                break
        except:
            pass

# 3. Если не нашли, показываем понятную ошибку
if not TELEGRAM_TOKEN:
    print("❌ ТОКЕН НЕ НАЙДЕН!")
    print("Создай Secret File с именем 'token.txt' и вставь туда токен.")
    print("ИЛИ добавь Environment Variable 'TELEGRAM_TOKEN'.")
    raise RuntimeError("TELEGRAM_TOKEN не найден")

# Импортируем бота только после того, как токен найден
import bot as bot_module

# Обновляем токен в модуле бота
bot_module.BOT_TOKEN = TELEGRAM_TOKEN
bot_module.bot = bot_module.telebot.TeleBot(TELEGRAM_TOKEN)
bot_module.CHANNEL_ID = os.environ.get('CHANNEL_ID', '@VibeDev_rus')

# ======= FLASK-СЕРВЕР =======
app = Flask(__name__)

@app.route('/')
def index():
    return "🤖 Бот работает! Токен загружен."

@app.route('/health')
def health():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    update = bot_module.telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot_module.bot.process_new_updates([update])
    return "OK", 200

# ======= ЗАПУСК =======
def run_bot():
    try:
        print("🚀 Запускаю бота...")
        bot_module.bot.polling(none_stop=True, interval=0)
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")

if __name__ == '__main__':
    print("✅ Токен загружен!")
    print(f"📢 Канал: {bot_module.CHANNEL_ID}")
    
    # Запускаем бота в потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем веб-сервер
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Запускаю Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
