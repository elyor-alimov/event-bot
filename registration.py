import asyncio
import json
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from database import (get_active_events, get_event, create_registration,
                      check_already_registered, get_or_create_user, save_qr_code,
                      get_user_registrations)
from languages import t
from qr_generator import generate_ticket
from sheets import add_registration_to_sheet, get_questions_for_event

# Шаги регистрации
FULL_NAME, ANSWERING = range(10, 12)

async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.first_name, user.last_name, user.username)
    lang = db_user["language"]

    events = await get_active_events()
    if not events:
        await update.message.reply_text(t(lang, "events_empty"))
        return

    keyboard = []
    for event in events:
        title = event["title_ru"] if lang == "ru" else event["title_uz"]
        event_type = "💻" if event["event_type"] == "online" else "🏢"
        keyboard.append([
            InlineKeyboardButton(
                f"{event_type} {title} — {event['event_date']}",
                callback_data=f"event_{event['id']}"
            )
        ])

    await update.message.reply_text(
        "📅 Выберите мероприятие:" if lang == "ru" else "📅 Tadbirni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_event_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event_id = int(query.data.replace("event_", ""))
    event = await get_event(event_id)
    db_user = await get_or_create_user(query.from_user.id, query.from_user.first_name)
    lang = db_user["language"]

    title = event["title_ru"] if lang == "ru" else event["title_uz"]
    desc = event["description_ru"] if lang == "ru" else event["description_uz"]
    event_type = "💻 Онлайн" if event["event_type"] == "online" else "🏢 Офлайн"
    if lang == "uz":
        event_type = "💻 Onlayn" if event["event_type"] == "online" else "🏢 Oflayn"

    location = ""
    if event["event_type"] == "offline":
        loc = event["location_ru"] if lang == "ru" else event["location_uz"]
        location = f"\n📍 {loc}" if loc else ""

    text = (
        f"📌 *{title}*\n"
        f"📅 {event['event_date']}\n"
        f"{event_type}{location}\n\n"
        f"{desc}"
    )

    already = await check_already_registered(query.from_user.id, event_id)
    if already:
        btn_text = "🎫 Показать мой билет" if lang == "ru" else "🎫 Chiptamni ko'rsatish"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(btn_text, callback_data=f"show_ticket_{event_id}")
        ]])
    else:
        btn_text = "📝 Зарегистрироваться" if lang == "ru" else "📝 Ro'yxatdan o'tish"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(btn_text, callback_data=f"register_{event_id}")
        ]])

    photo_url = event.get("photo_url", "")
    from sheets import convert_drive_link
    photo_url = convert_drive_link(photo_url)

    if photo_url:
        try:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=query.from_user.id,
                photo=photo_url,
                caption=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event_id = int(query.data.replace("register_", ""))
    context.user_data["reg_event_id"] = event_id
    context.user_data["reg_answers"] = {}
    context.user_data["reg_question_index"] = 0

    db_user = await get_or_create_user(query.from_user.id, query.from_user.first_name)
    lang = db_user["language"]
    context.user_data["reg_lang"] = lang

    # Загружаем кастомные вопросы
    event = await get_event(event_id)
    sheet_id = event.get("sheet_id", "")
    from database import get_event_questions
    questions = await get_event_questions(event_id)
    context.user_data["reg_questions"] = questions

    ask = "Введите ваше имя и фамилию:" if lang == "ru" else "Ism va familiyangizni kiriting:"
    try:
        await query.edit_message_text(ask)
    except Exception:
        await context.bot.send_message(chat_id=query.from_user.id, text=ask)
    return FULL_NAME

async def get_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["full_name"] = update.message.text
    context.user_data["reg_answers"]["full_name"] = update.message.text
    lang = context.user_data["reg_lang"]

    questions = context.user_data.get("reg_questions", [])

    if questions:
        # Есть кастомные вопросы — задаём первый
        context.user_data["reg_question_index"] = 0
        return await ask_next_question(update, context)
    else:
        # Нет вопросов — завершаем регистрацию
        return await finish_registration(update, context)

async def ask_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data["reg_lang"]
    questions = context.user_data["reg_questions"]
    idx = context.user_data["reg_question_index"]

    if idx >= len(questions):
        return await finish_registration(update, context)

    q = questions[idx]
    question_text = q["question_ru"] if lang == "ru" else q["question_uz"]

    options = q["options_ru"] if lang == "ru" else q.get("options_uz") or q["options_ru"]
    if q["type"] == "buttons" and options:
        keyboard = ReplyKeyboardMarkup(
            [[opt] for opt in options],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text(question_text, reply_markup=keyboard)
    else:
        # Текстовый вопрос
        await update.message.reply_text(
            question_text,
            reply_markup=ReplyKeyboardRemove()
        )

    return ANSWERING

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data["reg_lang"]
    questions = context.user_data["reg_questions"]
    idx = context.user_data["reg_question_index"]

    # Сохраняем ответ
    q = questions[idx]
    key = q["question_ru"]
    context.user_data["reg_answers"][key] = update.message.text

    # Следующий вопрос
    context.user_data["reg_question_index"] = idx + 1
    return await ask_next_question(update, context)

async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data["reg_lang"]
    event_id = context.user_data["reg_event_id"]
    event = await get_event(event_id)

    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.first_name, user.last_name, user.username)

    answers = json.dumps(context.user_data["reg_answers"], ensure_ascii=False)
    reg_id = await create_registration(db_user["id"], event_id, answers)
    title = event["title_ru"] if lang == "ru" else event["title_uz"]

    # Генерируем билет для офлайн
    ticket_path = None
    unique_code = None
    if event["event_type"] == "offline":
        ticket_path, unique_code = generate_ticket(
            registration_id=reg_id,
            event_title=event["title_ru"],
            event_date=event["event_date"],
            event_location=event.get("location_ru", ""),
            participant_name=context.user_data["full_name"],
            event_type="offline"
        )
        await save_qr_code(reg_id, unique_code)

    # Записываем в Google Sheets
    from datetime import datetime
    await asyncio.to_thread(
        add_registration_to_sheet,
        event["title_ru"],
        event["event_date"],
        context.user_data["full_name"],
        answers,
        datetime.now().strftime("%d.%m.%Y %H:%M")
    )

    # Отправляем подтверждение
    if event["event_type"] == "offline":
        loc = event.get("location_ru", "") if lang == "ru" else event.get("location_uz", "")
        msg = (
            f"✅ Вы зарегистрированы!\n\n"
            f"📌 {title}\n"
            f"📅 {event['event_date']}\n"
            f"📍 {loc}\n\n"
            f"🎫 Ваш билет ниже — сохраните его!"
        ) if lang == "ru" else (
            f"✅ Siz ro'yxatdan o'tdingiz!\n\n"
            f"📌 {title}\n"
            f"📅 {event['event_date']}\n"
            f"📍 {loc}\n\n"
            f"🎫 Chiptangiz quyida — saqlang!"
        )
        from keyboards import main_menu_keyboard
        await update.message.reply_text(msg, reply_markup=main_menu_keyboard(lang))
        await update.message.reply_photo(
            photo=open(ticket_path, "rb"),
            caption=f"Ваш код: `{unique_code}`" if lang == "ru" else f"Sizning kodingiz: `{unique_code}`",
            parse_mode="Markdown"
        )
    else:
        msg = (
            f"✅ Вы зарегистрированы!\n\n"
            f"📌 {title}\n"
            f"📅 {event['event_date']}\n"
            f"💻 Онлайн — ссылку пришлём накануне"
        ) if lang == "ru" else (
            f"✅ Siz ro'yxatdan o'tdingiz!\n\n"
            f"📌 {title}\n"
            f"📅 {event['event_date']}\n"
            f"💻 Onlayn — havola ertaga yuboriladi"
        )
        from keyboards import main_menu_keyboard
        await update.message.reply_text(msg, reply_markup=main_menu_keyboard(lang))

    context.user_data.clear()
    return ConversationHandler.END

async def show_my_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event_id = int(query.data.replace("show_ticket_", ""))
    event = await get_event(event_id)
    db_user = await get_or_create_user(query.from_user.id, query.from_user.first_name)
    lang = db_user["language"]

    from database import get_registration_by_user_and_event
    reg = await get_registration_by_user_and_event(query.from_user.id, event_id)

    if not reg or not reg["qr_code"]:
        msg = "Билет не найден." if lang == "ru" else "Chipta topilmadi."
        await query.edit_message_text(msg)
        return

    answers = json.loads(reg["answers"]) if reg["answers"] else {}
    participant_name = answers.get("full_name", query.from_user.first_name)

    ticket_path, _ = generate_ticket(
        registration_id=reg["id"],
        event_title=event["title_ru"],
        event_date=event["event_date"],
        event_location=event.get("location_ru", ""),
        participant_name=participant_name,
        event_type=event["event_type"]
    )

    await context.bot.send_photo(
        chat_id=query.from_user.id,
        photo=open(ticket_path, "rb"),
        caption=f"🎫 Ваш билет\nКод: `{reg['qr_code']}`" if lang == "ru" else f"🎫 Sizning chiptangiz\nKod: `{reg['qr_code']}`",
        parse_mode="Markdown"
    )

async def show_my_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.first_name, user.last_name, user.username)
    lang = db_user["language"]

    regs = await get_user_registrations(user.id)

    if not regs:
        msg = "У тебя пока нет записей." if lang == "ru" else "Sizda hali yozuvlar yo'q."
        await update.message.reply_text(msg)
        return

    msg = "📋 Твои записи:\n\n" if lang == "ru" else "📋 Mening yozuvlarim:\n\n"
    for r in regs:
        title = r["title_ru"] if lang == "ru" else r["title_uz"]
        status = "✅ Зарегистрирован" if lang == "ru" else "✅ Ro'yxatdan o'tgan"
        msg += f"📌 {title}\n📅 {r['event_date']}\n{status}\n\n"

    await update.message.reply_text(msg)

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Регистрация отменена.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

registration_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_registration, pattern="^register_")],
    states={
        FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
        ANSWERING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)],
    },
    fallbacks=[CommandHandler("cancel", cancel_registration)],
)