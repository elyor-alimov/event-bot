from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from database import get_user, create_event, get_active_events
from languages import t

# Шаги создания мероприятия
(
    TITLE_RU, TITLE_UZ,
    DESC_RU, DESC_UZ,
    DATE, EVENT_TYPE,
    LOCATION_RU, LOCATION_UZ,
    ONLINE_LINK
) = range(9)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user or not user["is_admin"]:
        await update.message.reply_text("⛔ У тебя нет доступа.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Создать мероприятие", callback_data="admin_create_event")],
        [InlineKeyboardButton("📋 Все мероприятия", callback_data="admin_list_events")],
    ])
    await update.message.reply_text("🔧 Админ панель:", reply_markup=keyboard)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "admin_list_events":
        events = await get_active_events()
        if not events:
            await query.edit_message_text("Мероприятий пока нет.")
            return
        text = "📋 Активные мероприятия:\n\n"
        for e in events:
            event_type = "💻 Онлайн" if e["event_type"] == "online" else "🏢 Офлайн"
            text += f"• {e['title_ru']} — {e['event_date']} {event_type}\n"
        await query.edit_message_text(text)

# ─── Создание мероприятия (шаг за шагом) ───────────────────

async def create_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Создание мероприятия\n\nШаг 1/6: Введи название на русском:")
    return TITLE_RU

async def get_title_ru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title_ru"] = update.message.text
    await update.message.reply_text("Шаг 2/6: Введи название на узбекском:")
    return TITLE_UZ

async def get_title_uz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title_uz"] = update.message.text
    await update.message.reply_text("Шаг 3/6: Описание на русском:")
    return DESC_RU

async def get_desc_ru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description_ru"] = update.message.text
    await update.message.reply_text("Шаг 4/6: Описание на узбекском:")
    return DESC_UZ

async def get_desc_uz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description_uz"] = update.message.text
    await update.message.reply_text("Шаг 5/6: Дата мероприятия (формат: 25.01.2026):")
    return DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_date"] = update.message.text
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏢 Офлайн", callback_data="type_offline"),
            InlineKeyboardButton("💻 Онлайн", callback_data="type_online")
        ]
    ])
    await update.message.reply_text("Шаг 6/6: Тип мероприятия:", reply_markup=keyboard)
    return EVENT_TYPE

async def get_event_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["event_type"] = query.data.replace("type_", "")

    if context.user_data["event_type"] == "offline":
        await query.edit_message_text("📍 Введи адрес/место на русском:")
        return LOCATION_RU
    else:
        await query.edit_message_text("🔗 Введи ссылку на трансляцию (или напиши 'позже'):")
        return ONLINE_LINK

async def get_location_ru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["location_ru"] = update.message.text
    await update.message.reply_text("📍 Введи адрес/место на узбекском:")
    return LOCATION_UZ

async def get_location_uz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["location_uz"] = update.message.text
    return await save_event(update, context)

async def get_online_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text
    context.user_data["online_link"] = None if link.lower() == "позже" else link
    return await save_event(update, context)

async def save_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    event_id = await create_event(data)
    await update.message.reply_text(
        f"✅ Мероприятие создано!\n\n"
        f"📌 {data['title_ru']}\n"
        f"📅 {data['event_date']}\n"
        f"🆔 ID: {event_id}"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Создание отменено.")
    return ConversationHandler.END

# ConversationHandler для создания мероприятия
create_event_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(create_event_start, pattern="^admin_create_event$")],
    states={
        TITLE_RU: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title_ru)],
        TITLE_UZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title_uz)],
        DESC_RU: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_desc_ru)],
        DESC_UZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_desc_uz)],
        DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
        EVENT_TYPE: [CallbackQueryHandler(get_event_type, pattern="^type_")],
        LOCATION_RU: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location_ru)],
        LOCATION_UZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location_uz)],
        ONLINE_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_online_link)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)