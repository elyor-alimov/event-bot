import asyncio
from sheets import sync_events_to_db, get_spreadsheet, ensure_sheet
from database import DB_PATH
import aiosqlite
import json
from sheets import sync_events_to_db, get_questions_for_event

async def sync_events():
    """Синхронизирует мероприятия из Google Sheets в локальную БД"""
    try:
        rows = sync_events_to_db()
    except Exception as e:
        print(f"Ошибка чтения Sheets: {e}")
        return 0

    if not rows:
        print("Нет мероприятий в таблице")
        return 0

    synced = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for row in rows:
            # Пропускаем пустые строки
            if not row.get("Название RU"):
                continue

            sheet_id = str(row.get("ID", "")).strip()
            if not sheet_id:
                continue

            is_active = 1 if str(row.get("Активно", "")).upper() == "ДА" else 0
            reg_open = 1 if str(row.get("Регистрация открыта", "")).upper() == "ДА" else 0
            event_type = "online" if str(row.get("Тип", "")).lower() == "online" else "offline"

            # Проверяем есть ли уже в БД по sheet_id
            async with db.execute(
                "SELECT id FROM events WHERE sheet_id = ?", (sheet_id,)
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                # Обновляем
                await db.execute("""
                    UPDATE events SET
                        title_ru = ?, title_uz = ?,
                        description_ru = ?, description_uz = ?,
                        event_date = ?, event_type = ?,
                        location_ru = ?, location_uz = ?,
                        photo_url = ?,
                        is_active = ?, registration_open = ?
                    WHERE sheet_id = ?
                """, (
                    row.get("Название RU", ""),
                    row.get("Название UZ", ""),
                    row.get("Описание RU", ""),
                    row.get("Описание UZ", ""),
                    row.get("Дата", ""),
                    event_type,
                    row.get("Адрес RU", ""),
                    row.get("Адрес UZ", ""),
                    row.get("Фото (ссылка)", ""),
                    is_active, reg_open,
                    sheet_id
                ))
            else:
                # Создаём новое
                await db.execute("""
                    INSERT INTO events
                    (sheet_id, title_ru, title_uz, description_ru, description_uz,
                     event_date, event_type, location_ru, location_uz,
                     photo_url, is_active, registration_open)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sheet_id,
                    row.get("Название RU", ""),
                    row.get("Название UZ", ""),
                    row.get("Описание RU", ""),
                    row.get("Описание UZ", ""),
                    row.get("Дата", ""),
                    event_type,
                    row.get("Адрес RU", ""),
                    row.get("Адрес UZ", ""),
                    row.get("Фото (ссылка)", ""),
                    is_active, reg_open
                ))
            synced += 1

            # Синхронизируем вопросы для этого мероприятия
            questions = await asyncio.to_thread(get_questions_for_event, sheet_id)
            await db.execute("DELETE FROM event_questions WHERE event_id = (SELECT id FROM events WHERE sheet_id = ?)", (sheet_id,))
            for q in questions:
                await db.execute("""
                    INSERT INTO event_questions (event_id, question_ru, question_uz, question_type, options)
                    SELECT id, ?, ?, ?, ? FROM events WHERE sheet_id = ?
                """, (
                    q["question_ru"], q["question_uz"],
                    q["type"],
                    json.dumps({"ru": q.get("options_ru", []), "uz": q.get("options_uz", [])}, ensure_ascii=False),
                    sheet_id
                ))

        await db.commit()

    print(f"Синхронизировано мероприятий: {synced} ✅")
    return synced