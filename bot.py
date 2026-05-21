from database import init_db, get_or_create_user, set_user_language, get_user

import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from languages import t
from keyboards import language_keyboard, main_menu_keyboard
from admin import admin_panel, admin_callback, create_event_conv
from registration import show_events, show_event_detail, registration_conv, show_my_ticket, show_my_registrations
from sync import sync_events
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web
from api import create_app
import asyncio

logging.basicConfig(level=logging.INFO)
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Временное хранилище языков (потом перенесём в БД)
user_languages = {}

async def get_lang_async(user_id: int) -> str:
    user = await get_user(user_id)
    if user and user.get("language"):
        return user["language"]
    return user_languages.get(user_id, "ru")

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(
        telegram_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )
    lang = db_user.get("language", "")

    # Если язык не выбран — спрашиваем
    if lang not in ["ru", "uz"]:
        await update.message.reply_text(
            "Выберите язык / Tilni tanlang:",
            reply_markup=language_keyboard()
        )
    else:
        # Язык уже есть — показываем меню
        await update.message.reply_text(
            t(lang, "welcome", name=user.first_name),
            reply_markup=main_menu_keyboard(lang)
        )

# Выбор языка через кнопки
async def handle_language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = query.data.replace("lang_", "")
    user_languages[user_id] = lang
    await set_user_language(user_id, lang)
    await query.edit_message_text(t(lang, "language_set"))
    await context.bot.send_message(
        chat_id=user_id,
        text=t(lang, "welcome", name=query.from_user.first_name),
        reply_markup=main_menu_keyboard(lang)
    )

# Кнопка смены языка
async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите язык / Tilni tanlang:",
        reply_markup=language_keyboard()
    )

# Обработка кнопок меню
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = await get_lang_async(user_id)
    text = update.message.text

    if text == t(lang, "btn_events"):
        await show_events(update, context)

    elif text == t(lang, "btn_my_registrations"):
        await show_my_registrations(update, context)

    elif text == t(lang, "btn_change_language"):
        await change_language(update, context)

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Твой Telegram ID: `{update.effective_user.id}`",
    parse_mode="Markdown")

async def manual_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user or not user["is_admin"]:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("🔄 Синхронизирую...")
    count = await sync_events()
    await update.message.reply_text(f"✅ Синхронизировано мероприятий: {count}")

async def volunteer_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scanner_url = "https://elyor-alimov.github.io/event-scanner/?token=volunteer2025"
    await update.message.reply_text(
        f"🔍 Ссылка для сканирования:\n{scanner_url}"
    )

async def post_init(application):
    await init_db()
    print("База данных готова ✅")
    await sync_events()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(sync_events, "interval", minutes=5)
    scheduler.start()
    print("Автосинхронизация запущена ✅")

    try:
        api_app = create_app()
        runner = web.AppRunner(api_app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        print("API сервер запущен на порту 8080 ✅")
    except Exception as e:
        print(f"❌ Ошибка запуска API: {e}")

async def show_my_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.first_name, user.last_name, user.username)
    lang = db_user["language"]

    from database import get_user_registrations
    regs = await get_user_registrations(user.id)

    if not regs:
        msg = "У тебя пока нет записей." if lang == "ru" else "Sizda hali yozuvlar yo'q."
        await update.message.reply_text(msg)
        return

    msg = "📋 Твои записи:\n\n" if lang == "ru" else "📋 Mening yozuvlarim:\n\n"
    for r in regs:
        title = r["title_ru"] if lang == "ru" else r["title_uz"]
        status_map = {
            "registered": "✅ Зарегистрирован" if lang == "ru" else "✅ Ro'yxatdan o'tgan",
        }
        status = status_map.get(r["status"], r["status"])
        msg += f"📌 {title}\n📅 {r['event_date']}\n{status}\n\n"

    await update.message.reply_text(msg)

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(registration_conv)
    app.add_handler(CallbackQueryHandler(show_event_detail, pattern="^event_"))
    # Сначала ConversationHandler - он должен быть первым
    app.add_handler(create_event_conv)

    # Потом команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("sync", manual_sync))
    app.add_handler(CommandHandler("qrscan", volunteer_check))

    # Потом callback кнопки
    app.add_handler(CallbackQueryHandler(handle_language_choice, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    # В самом конце - общий обработчик текста
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    # Тут видимо кнопка для показа билета, которая появляется после регистрации

    app.add_handler(CallbackQueryHandler(show_my_ticket, pattern="^show_ticket_"))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()