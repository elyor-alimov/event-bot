import asyncio
from datetime import datetime
from sheets import ensure_sheet, convert_drive_link
from database import DB_PATH
import aiosqlite

async def get_users_for_blast(target, event_id=None):
    """Возвращает список пользователей для рассылки"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if target == 'ВСЕ':
            async with db.execute(
                "SELECT telegram_id, language FROM users"
            ) as cursor:
                rows = await cursor.fetchall()

        elif target == 'ЗАРЕГАНЫ' and event_id:
            async with db.execute("""
                SELECT u.telegram_id, u.language
                FROM registrations r
                JOIN users u ON r.user_id = u.id
                WHERE r.event_id = ? AND r.status != 'cancelled'
            """, (event_id,)) as cursor:
                rows = await cursor.fetchall()

        elif target == 'ПРИШЛИ' and event_id:
            async with db.execute("""
                SELECT u.telegram_id, u.language
                FROM registrations r
                JOIN users u ON r.user_id = u.id
                WHERE r.event_id = ? AND r.attended = 1
            """, (event_id,)) as cursor:
                rows = await cursor.fetchall()

        elif target == 'ПОДТВЕРДИЛИ' and event_id:
            async with db.execute("""
                SELECT u.telegram_id, u.language
                FROM registrations r
                JOIN users u ON r.user_id = u.id
                WHERE r.event_id = ? AND r.confirmed = 1
            """, (event_id,)) as cursor:
                rows = await cursor.fetchall()
        else:
            rows = []

        return [dict(r) for r in rows]

async def send_blast(bot, row_index, row, events_map):
    """Отправляет одну рассылку"""
    target = str(row.get('Кому', '')).upper().strip()
    event_id_str = str(row.get('ID мероприятия', '')).strip()
    text_ru = row.get('Текст RU', '')
    text_uz = row.get('Текст UZ', '')
    media_url = row.get('Файл (ссылка)', '')
    media_type = row.get('Тип файла', '').lower().strip()

    if not text_ru:
        return 0

    # Находим event_id если нужен
    event_id = None
    if event_id_str:
        event = events_map.get(event_id_str)
        if event:
            event_id = event['id']

    users = await get_users_for_blast(target, event_id)
    if not users:
        print(f"Нет пользователей для рассылки: {target}")
        return 0

    sent = 0
    for user in users:
        lang = user.get('language', 'ru')
        text = text_ru if lang == 'ru' else (text_uz or text_ru)

        try:
            if media_url and media_type:
                file_url = convert_drive_link(media_url)
                import aiohttp
                from io import BytesIO

                async with aiohttp.ClientSession() as session:
                    async with session.get(file_url) as resp:
                        file_bytes = await resp.read()
                buf = BytesIO(file_bytes)

                if media_type in ['фото', 'photo', 'image', 'png', 'jpg']:
                    buf.name = 'photo.jpg'
                    await bot.send_photo(chat_id=user['telegram_id'], photo=buf, caption=text)
                elif media_type in ['видео', 'video', 'mp4']:
                    buf.name = 'video.mp4'
                    await bot.send_video(chat_id=user['telegram_id'], video=buf, caption=text)
                elif media_type in ['гиф', 'gif']:
                    buf.name = 'anim.gif'
                    await bot.send_animation(chat_id=user['telegram_id'], animation=buf, caption=text)
                elif media_type in ['аудио', 'audio', 'mp3']:
                    buf.name = 'audio.mp3'
                    await bot.send_audio(chat_id=user['telegram_id'], audio=buf, caption=text)
                elif media_type in ['голосовое', 'voice', 'ogg']:
                    buf.name = 'voice.ogg'
                    await bot.send_voice(chat_id=user['telegram_id'], voice=buf, caption=text)
                elif media_type in ['pdf', 'документ', 'document', 'doc']:
                    buf.name = 'document.pdf'
                    await bot.send_document(chat_id=user['telegram_id'], document=buf, caption=text)
                else:
                    await bot.send_message(chat_id=user['telegram_id'], text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Ошибка рассылки {user['telegram_id']}: {e}")

    # Отмечаем как отправленное
    if sent > 0:
        ws = ensure_sheet('Рассылки')
        ws.update_cell(row_index + 2, 7, f'ОТПРАВЛЕНО {datetime.now().strftime("%d.%m %H:%M")}')
        print(f"Рассылка отправлена {sent} пользователям")

    return sent

async def run_blasts(bot):
    """Запускает все рассылки со статусом ГОТОВО"""
    try:
        ws = ensure_sheet('Рассылки')
        rows = ws.get_all_records()

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM events") as cursor:
                events_list = await cursor.fetchall()
                events_map = {str(e['sheet_id']): dict(e) for e in events_list if e['sheet_id']}

        total = 0
        for i, row in enumerate(rows):
            status = str(row.get('Статус', '')).upper().strip()
            if status != 'ГОТОВО':
                continue
            sent = await send_blast(bot, i, row, events_map)
            total += sent

        return total
    except Exception as e:
        print(f"Ошибка рассылки: {e}")
        return 0