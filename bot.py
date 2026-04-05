import os
import sqlite3
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Загрузка переменных из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "attendance.db")


def init_db():
    """Инициализация базы данных."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS absences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            absence_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_date
        ON absences(user_id, absence_date)
    """)
    conn.commit()
    conn.close()


def register_user(user):
    """Регистрация или обновление информации о пользователе."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT INTO users (user_id, username, first_name, last_name)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   username=excluded.username,
                   first_name=excluded.first_name,
                   last_name=excluded.last_name,
                   last_seen=CURRENT_TIMESTAMP""",
            (user.id, user.username, user.first_name, user.last_name),
        )
        conn.commit()
    finally:
        conn.close()


def get_db_connection():
    """Получение соединения с БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_keyboard():
    """Создаёт главное меню с кнопками."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Меня сегодня не будет", callback_data="absent_today")],
        [InlineKeyboardButton("Мои пропуски", callback_data="my_absences")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    register_user(user)
    await update.message.reply_text(
        f"Привет, {user.first_name}! Выбери действие:",
        reply_markup=get_keyboard(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline-кнопки."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    action = query.data

    if action == "absent_today":
        await mark_absent(query, user)
    elif action == "my_absences":
        await show_absences(query, user)


async def mark_absent(query, user):
    """Отметить отсутствие сегодня."""
    today = datetime.now().strftime("%Y-%m-%d")

    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO absences (user_id, absence_date)
               VALUES (?, ?)""",
            (user.id, today),
        )
        conn.commit()

        cursor = conn.execute("SELECT changes() as changes")
        row = cursor.fetchone()

        if row["changes"] > 0:
            message = f"Записал! Вас не будет сегодня ({today})."
        else:
            message = f"Вы уже отмечены на сегодня ({today})."
    finally:
        conn.close()

    await query.edit_message_text(
        f"{message}\n\nВыбери действие:",
        reply_markup=get_keyboard(),
    )


async def show_absences(query, user):
    """Показать все пропуски пользователя."""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """SELECT a.absence_date, a.created_at
               FROM absences a
               WHERE a.user_id = ? ORDER BY a.absence_date DESC""",
            (user.id,),
        )
        rows = cursor.fetchall()

        if not rows:
            text = "У вас пока нет пропусков."
        else:
            total = len(rows)
            text = f"Ваши пропуски (всего: {total}):\n\n"
            for row in rows:
                date_str = row["absence_date"]
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                text += f"• {formatted_date}\n"

            if len(text) > 4000:
                text = text[:4000] + "\n... и так далее"
    finally:
        conn.close()

    await query.edit_message_text(
        f"{text}\nВыбери действие:",
        reply_markup=get_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    text = (
        "Доступные команды:\n"
        "/start - Главное меню с кнопками\n"
        "/absent - Отметить отсутствие сегодня\n"
        "/myabsences - Посмотреть мои пропуски\n"
        "/help - Эта справка"
    )
    await update.message.reply_text(text)


async def absent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /absent."""
    user = update.effective_user
    register_user(user)
    today = datetime.now().strftime("%Y-%m-%d")

    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO absences (user_id, absence_date)
               VALUES (?, ?)""",
            (user.id, today),
        )
        conn.commit()

        cursor = conn.execute("SELECT changes() as changes")
        row = cursor.fetchone()

        if row["changes"] > 0:
            message = f"Записал! Вас не будет сегодня ({today})."
        else:
            message = f"Вы уже отмечены на сегодня ({today})."
    finally:
        conn.close()

    await update.message.reply_text(
        f"{message}\n\nВыбери действие:",
        reply_markup=get_keyboard(),
    )


async def myabsences_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /myabsences."""
    user = update.effective_user

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """SELECT absence_date FROM absences
               WHERE user_id = ? ORDER BY absence_date DESC""",
            (user.id,),
        )
        rows = cursor.fetchall()

        if not rows:
            text = "У тебя пока нет пропусков."
        else:
            total = len(rows)
            text = f"Твои пропуски (всего: {total}):\n\n"
            for row in rows:
                date_str = row["absence_date"]
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                text += f"• {formatted_date}\n"
    finally:
        conn.close()

    await update.message.reply_text(
        f"{text}\nВыбери действие:",
        reply_markup=get_keyboard(),
    )


async def main():
    """Запуск бота."""
    init_db()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Не найден токен бота! Установите переменную окружения TELEGRAM_BOT_TOKEN")
        return

    application = Application.builder().token(token).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("absent", absent_command))
    application.add_handler(CommandHandler("myabsences", myabsences_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Запуск бота
    logger.info("Бот запущен!")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    # Держим бота запущенным
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        await application.stop()
        await application.updater.stop()


if __name__ == "__main__":
    asyncio.run(main())
