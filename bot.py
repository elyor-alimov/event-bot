from database import init_db, get_or_create_user, set_user_language, get_user
import logging
import os
import aiosqlite
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
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
from reminders import check_and_send_reminders
from blasts import run_blasts

logging.basicConfig(level=logging.INFO)
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

user_languages = {}

async def get_lang_async(user_id: int) -> str:
    user = await get_user(user_id)
    if user and user.get("language"):
        return user["language"]
    return user_languages.get(user_id, "ru")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(
        telegram_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )
    lang = db_user.get("language", "")
    if lang not in ["ru", "uz"]:
        await update.message.reply_text(
            "Выберите язык / Tilni tanlang:",
            reply_markup=language_keyboard()
        )
    else:
        await update.message.reply_text(
            t(lang, "welcome", name=user.first_name),
            reply_markup=main_menu_keyboard(lang)
        )

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

async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите язык / Tilni tanlang:",
        reply_markup=language_keyboard()
    )

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
    await update.message.reply_text(
        f"Твой Telegram ID: `{update.effective_user.id}`",
        parse_mode="Markdown"
    )

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
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📷 Открыть сканер", web_app=WebAppInfo(url=scanner_url))
    ]])
    await update.message.reply_text("Нажми кнопку чтобы открыть сканер:", reply_markup=keyboard)

async def test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user or not user["is_admin"]:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("🔄 Проверяю напоминания...")
    await check_and_send_reminders(context.bot)
    await update.message.reply_text("✅ Готово!")

async def blast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user or not user["is_admin"]:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("📨 Запускаю рассылку...")
    total = await run_blasts(context.bot)
    await update.message.reply_text(f"✅ Рассылка завершена — отправлено {total} сообщений")

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    db_user = await get_user(user_id)
    lang = db_user.get('language', 'ru') if db_user else 'ru'

    if data.startswith('confirm_yes_'):
        event_id = int(data.replace('confirm_yes_', ''))
        async with aiosqlite.connect('data/bot.db') as db:
            await db.execute("""
                UPDATE registrations SET confirmed=1
                WHERE event_id=? AND user_id=(SELECT id FROM users WHERE telegram_id=?)
            """, (event_id, user_id))
            await db.commit()
        msg = "✅ Отлично, ждём тебя!" if lang == 'ru' else "✅ Zo'r, sizni kutamiz!"

    elif data.startswith('confirm_no_'):
        event_id = int(data.replace('confirm_no_', ''))
        async with aiosqlite.connect('data/bot.db') as db:
            await db.execute("""
                UPDATE registrations SET confirmed=0, status='declined'
                WHERE event_id=? AND user_id=(SELECT id FROM users WHERE telegram_id=?)
            """, (event_id, user_id))
            await db.commit()
        msg = "Жаль, в следующий раз! 👋" if lang == 'ru' else "Keyingi safar! 👋"

    await query.edit_message_text(msg)

async def post_init(application):
    await init_db()
    print("База данных готова ✅")
    await sync_events()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(sync_events, "interval", minutes=5)
    scheduler.add_job(check_and_send_reminders, "interval", minutes=30, args=[application.bot])
    scheduler.add_job(run_blasts, "interval", minutes=30, args=[application.bot])
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

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(registration_conv)
    app.add_handler(create_event_conv)
    app.add_handler(CallbackQueryHandler(show_event_detail, pattern="^event_"))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("sync", manual_sync))
    app.add_handler(CommandHandler("qrscan", volunteer_check))
    app.add_handler(CommandHandler("testreminder", test_reminder))
    app.add_handler(CommandHandler("blast", blast))

    app.add_handler(CallbackQueryHandler(handle_language_choice, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(handle_confirmation, pattern="^confirm_"))
    app.add_handler(CallbackQueryHandler(show_my_ticket, pattern="^show_ticket_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()