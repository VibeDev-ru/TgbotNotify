import os
import sys
import subprocess
import threading
from flask import Flask, request

# ====================================================
# ПРИНУДИТЕЛЬНАЯ УСТАНОВКА ЗАВИСИМОСТЕЙ
# ====================================================
print("📦 Проверяю установку зависимостей...")
try:
    import telebot
    print("✅ telebot уже установлен")
except ImportError:
    print("⚠️ telebot не найден, устанавливаю...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("✅ Зависимости установлены!")

# ====================================================
# ФУНКЦИЯ ДЛЯ ПОИСКА И ОЧИСТКИ ТОКЕНА
# ====================================================
def find_and_clean_token():
    """Ищет токен в разных местах и очищает от пробелов"""
    token = None
    
    # 1. Проверяем переменные окружения
    token = os.environ.get('TELEGRAM_TOKEN')
    
    # 2. Ищем в секретных файлах
    if not token:
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
                            # Берем часть после знака =
                            if '=' in line:
                                token = line.split('=', 1)[1]
                            else:
                                token = line
                            break
                    # Если не нашли по ключу, берем весь контент
                    if not token:
                        token = content
                    print(f"✅ Токен найден в {path}")
                    break
            except Exception as e:
                print(f"⚠️ Не удалось прочитать {path}: {e}")
    
    # 3. Очищаем токен от ВСЕХ пробелов, переносов и табуляций
    if token:
        # Удаляем все виды пробелов
        token = token.replace(' ', '')
        token = token.replace('\n', '')
        token = token.replace('\r', '')
        token = token.replace('\t', '')
        token = token.strip()
        
        # Если токен начинается с кавычек, убираем их
        if token.startswith('"') and token.endswith('"'):
            token = token[1:-1]
        if token.startswith("'") and token.endswith("'"):
            token = token[1:-1]
    
    return token

# ====================================================
# ПОИСК ТОКЕНА
# ====================================================
TELEGRAM_TOKEN = find_and_clean_token()

if not TELEGRAM_TOKEN:
    print("❌ ТОКЕН НЕ НАЙДЕН!")
    print("Создай Secret File с именем '.env' и содержимым:")
    print("TELEGRAM_TOKEN=твой_токен")
    raise RuntimeError("TELEGRAM_TOKEN не найден")

print(f"✅ Токен загружен (длина: {len(TELEGRAM_TOKEN)} символов)")
print(f"✅ Токен начинается с: {TELEGRAM_TOKEN[:10]}...")

# ====================================================
# ИМПОРТ И НАСТРОЙКА БОТА
# ====================================================
import bot as bot_module

# Обновляем токен в модуле бота
bot_module.BOT_TOKEN = TELEGRAM_TOKEN

# ПЕРЕСОЗДАЕМ БОТА С ЧИСТЫМ ТОКЕНОМ
import telebot
bot_module.bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Читаем CHANNEL_ID
CHANNEL_ID = os.environ.get('CHANNEL_ID')
if not CHANNEL_ID:
    try:
        with open('/etc/secrets/.env', 'r') as f:
            for line in f:
                if 'CHANNEL_ID' in line:
                    CHANNEL_ID = line.split('=', 1)[1].strip().replace(' ', '')
                    break
    except:
        pass

if not CHANNEL_ID:
    CHANNEL_ID = '@VibeDev_rus'

bot_module.CHANNEL_ID = CHANNEL_ID
print(f"📢 Канал: {CHANNEL_ID}")

# ====================================================
# FLASK-СЕРВЕР
# ====================================================
app = Flask(__name__)

@app.route('/')
def index():
    return "🤖 Бот работает! Токен загружен."

@app.route('/health')
def health():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot_module.bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
        return "ERROR", 500

# ====================================================
# ЗАПУСК БОТА В ПОТОКЕ
# ====================================================
def run_bot():
    try:
        print("🚀 Запускаю бота...")
        bot_module.bot.polling(none_stop=True, interval=0)
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")

if __name__ == '__main__':
    print("✅ Все настройки загружены!")
    
    # Запускаем бота в потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем веб-сервер
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Запускаю Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
