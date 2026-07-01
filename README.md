# Telegram Bot on Render (Free) — Flask + Polling

Готовый минимальный проект, чтобы запустить Telegram-бота на **Render Free Web Service** без ошибки
«No open ports detected». Веб-сервер Flask занимает порт `$PORT`, Telegram-бот работает через `run_polling()`
в фоне (отдельный поток).

## Что внутри
- `app.py` — Flask (`/` и `/health`) + запуск Telegram-бота в отдельном потоке.
- `requirements.txt` — зависимости.
- `render.yaml` — опционально, блюпринт для автосоздания сервиса на Render.
- `.gitignore` — базовое.

---

## Быстрый старт локально

1) Установите зависимости (желательно в виртуальном окружении):
```bash
pip install -r requirements.txt
```

2) Экспортируйте токен (замените на свой от @BotFather):
```bash
export TELEGRAM_TOKEN=1234567890:ABCDEF...
```

3) Запустите:
```bash
python app.py
```

4) Проверьте в браузере:
- http://127.0.0.1:5000/  → `Bot is running`
- http://127.0.0.1:5000/health → `OK`

В Telegram бот должен отвечать на `/start`.

---

## Деплой на Render (через Dashboard)

1) Залейте файлы в **новый репозиторий GitHub** (в корне должны быть `app.py` и `requirements.txt`).
2) На https://render.com создайте **New → Web Service** и подключите репозиторий.
3) Настройки сервиса:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
   - **Environment → Add Environment Variable:**
     - Key: `TELEGRAM_TOKEN`
     - Value: `ваш_токен_бота`
4) Нажмите **Deploy**.

После деплоя Render выдаст Public URL вида `https://<имя>.onrender.com`.
Проверьте:
- `https://<имя>.onrender.com/` → `Bot is running`
- `https://<имя>.onrender.com/health` → `OK`

Если видите ошибку «No open ports detected» — значит процесс не слушает `$PORT`.
В этом проекте Flask запускается с `host=0.0.0.0` и `port=os.environ["PORT"]`, что исправляет проблему.

---

## Автопросыпание (чтобы Render Free не засыпал)

Render Free усыпляет веб-сервис приблизительно через 15 минут без входящего трафика.
Чтобы бот был доступен 24/7, можно настроить внешний мониторинг, который
будет обращаться к `https://<имя>.onrender.com/health` каждые 1–5 минут.

---

## Типичные ошибки и решения

- **`No open ports detected`** — убедитесь, что `web.run(host="0.0.0.0", port=int(os.environ["PORT"]))` действительно выполняется.
- **`KeyError: 'TELEGRAM_TOKEN'`** — добавьте переменную окружения в Render → Environment.
- **Бот не отвечает** — пересоздайте токен у @BotFather и обновите `TELEGRAM_TOKEN`.
- **ModuleNotFoundError** — проверьте, что библиотека есть в `requirements.txt`.

---

## Вариант с Webhook (опционально)

Можно заменить polling на webhook и слушать `$PORT` встроенным сервером `python-telegram-bot`.
Тогда достаточно `app.run_webhook(...)` без Flask. Для упрощения данный проект использует polling.
