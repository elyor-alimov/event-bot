import asyncio
from datetime import datetime, timedelta
from sheets import ensure_sheet
from database import DB_PATH
import aiosqlite
from datetime import timezone
import pytz

TZ = pytz.timezone('Asia/Tashkent')

async def get_registrations_for_event(event_id):
    """Возвращает telegram_id всех зарегистрированных на мероприятие"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.telegram_id, u.language, r.status, r.confirmed
            FROM registrations r
            JOIN users u ON r.user_id = u.id
            WHERE r.event_id = ? AND r.status != 'cancelled'
        """, (event_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_confirmed_registrations(event_id):
    """Только подтвердившие участие"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.telegram_id, u.language
            FROM registrations r
            JOIN users u ON r.user_id = u.id
            WHERE r.event_id = ? AND r.confirmed = 1
        """, (event_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def send_reminder(bot, event_id, row_index, row, events_map):
    """Отправляет одно напоминание"""
    import re

    sheet_event_id = str(row.get('ID мероприятия', '')).strip()
    print(f"DEBUG send_reminder: sheet_event_id='{sheet_event_id}', events_map keys={list(events_map.keys())}")
    event = events_map.get(sheet_event_id)
    print(f"DEBUG: event найден: {event is not None}")
    if not event:
        print(f"DEBUG: мероприятие не найдено для ID '{sheet_event_id}'")
        return
    hours_before = row.get('За сколько часов', '')
    text_ru = row.get('Текст RU', '')
    text_uz = row.get('Текст UZ', '')
    media_url = row.get('Файл (ссылка)', '')
    media_type = row.get('Тип файла', '').lower().strip()
    only_confirmed = str(row.get('Только подтвердившим', '')).upper() == 'ДА'

    if not sheet_event_id or hours_before == '' or not text_ru:
        print(f"DEBUG: недостаточно данных для напоминания")
        return

    # Находим мероприятие
    event = events_map.get(sheet_event_id)
    if not event:
        return

    # Проверяем время
    try:
        event_time = event.get('event_time') or '00:00'
        event_dt = datetime.strptime(
            f"{event['event_date']} {event_time}",
            '%d.%m.%Y %H:%M'
        )
        event_dt = TZ.localize(event_dt)
        send_time = event_dt - timedelta(hours=int(hours_before))
        now = datetime.now(TZ)
        print(f"DEBUG: событие={event_dt}, отправить в={send_time}, сейчас={now}")
        if not (send_time <= now <= send_time + timedelta(minutes=30)):
            print(f"DEBUG: время не подошло")
            return
    except Exception as e:
        print(f"Ошибка времени: {e}")
        return

    # Получаем участников
    if only_confirmed:
        users = await get_confirmed_registrations(event['id'])
    else:
        users = await get_registrations_for_event(event['id'])

    if not users:
        return

    sent = 0
    for user in users:
        lang = user.get('language', 'ru')
        text = text_ru if lang == 'ru' else (text_uz or text_ru)

        try:
            if media_url and media_type:
                from sheets import convert_drive_link
                file_url = convert_drive_link(media_url)
                if media_type in ['фото', 'photo', 'image']:
                    await bot.send_photo(chat_id=user['telegram_id'], photo=file_url, caption=text)
                elif media_type in ['видео', 'video']:
                    await bot.send_video(chat_id=user['telegram_id'], video=file_url, caption=text)
                elif media_type in ['pdf', 'документ', 'document']:
                    await bot.send_document(chat_id=user['telegram_id'], document=file_url, caption=text)
                else:
                    await bot.send_message(chat_id=user['telegram_id'], text=text)
            else:
                await bot.send_message(chat_id=user['telegram_id'], text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Ошибка отправки напоминания {user['telegram_id']}: {e}")

    # Отмечаем как отправленное
    if sent > 0:
        ws = ensure_sheet('Напоминания')
        ws.update_cell(row_index + 2, 7, f'ОТПРАВЛЕНО {datetime.now().strftime("%d.%m %H:%M")}')
        print(f"Напоминание отправлено {sent} участникам")

async def check_and_send_reminders(bot):
    try:
        ws = ensure_sheet('Напоминания')
        rows = ws.get_all_records()
        print(f"DEBUG: найдено напоминаний в таблице: {len(rows)}")

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM events WHERE is_active=1") as cursor:
                events_list = await cursor.fetchall()
                events_map = {str(e['sheet_id']): dict(e) for e in events_list if e['sheet_id']}
        print(f"DEBUG: мероприятий в БД: {len(events_map)}, ключи: {list(events_map.keys())}")

        for i, row in enumerate(rows):
            print(f"DEBUG: строка {i}: {row}")
            if str(row.get('Отправлено', '')).startswith('ОТПРАВЛЕНО'):
                print(f"DEBUG: строка {i} уже отправлена, пропускаем")
                continue
            await send_reminder(bot, i, i, row, events_map)

    except Exception as e:
        print(f"Ошибка проверки напоминаний: {e}")

async def send_confirmation_request(bot, event_id, event_title, event_date):
    """Отправляет запрос подтверждения участия за 1 день"""
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

    users = await get_registrations_for_event(event_id)

    for user in users:
        lang = user.get('language', 'ru')
        if lang == 'ru':
            text = f"👋 Привет!\n\nЗавтра мероприятие:\n📌 {event_title}\n📅 {event_date}\n\nВы придёте?"
            btn_yes = "✅ Да, приду"
            btn_no = "❌ Не смогу"
        else:
            text = f"👋 Salom!\n\nErtaga tadbir:\n📌 {event_title}\n📅 {event_date}\n\nKelasizmi?"
            btn_yes = "✅ Ha, kelaman"
            btn_no = "❌ Kela olmayman"

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(btn_yes, callback_data=f"confirm_yes_{event_id}"),
            InlineKeyboardButton(btn_no, callback_data=f"confirm_no_{event_id}")
        ]])

        try:
            await bot.send_message(
                chat_id=user['telegram_id'],
                text=text,
                reply_markup=keyboard
            )
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Ошибка отправки подтверждения: {e}")