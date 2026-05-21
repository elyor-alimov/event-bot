from aiohttp import web
import json
from database import DB_PATH
import aiosqlite
from datetime import datetime
from sheets import mark_attended, ensure_sheet

VOLUNTEER_TOKEN = "volunteer2025"

async def get_events(request):
    token = request.rel_url.query.get('token', '')
    if token != VOLUNTEER_TOKEN:
        return web.json_response({'error': 'unauthorized'}, status=401)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM events WHERE is_active=1 AND registration_open=1 ORDER BY event_date"
        ) as cursor:
            rows = await cursor.fetchall()
            events = []
            for r in rows:
                events.append({
                    'id': r['id'],
                    'title': r['title_ru'],
                    'date': r['event_date'],
                    'type': r['event_type']
                })

    return web.json_response({'events': events}, headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, ngrok-skip-browser-warning'
    })

async def scan_qr(request):
    data = await request.json()
    if data.get('token') != VOLUNTEER_TOKEN:
        return web.json_response({'error': 'unauthorized'}, status=401)

    code = data.get('code', '').strip()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT r.*, e.title_ru, e.event_date, e.event_type,
                   u.first_name, u.last_name
            FROM registrations r
            JOIN events e ON r.event_id = e.id
            JOIN users u ON r.user_id = u.id
            WHERE r.qr_code = ?
        """, (code,)) as cursor:
            reg = await cursor.fetchone()

        if not reg:
            return web.json_response({'status': 'not_found'}, headers={
                'Access-Control-Allow-Origin': '*'
            })

        reg = dict(reg)

        try:
            event_date = datetime.strptime(reg['event_date'], '%d.%m.%Y')
            if event_date.date() < datetime.now().date():
                return web.json_response({
                    'status': 'expired',
                    'message': 'Билет недействителен',
                    'detail': f"Мероприятие {reg['event_date']} уже прошло"
                }, headers={'Access-Control-Allow-Origin': '*'})
        except:
            pass

        if reg['attended']:
            attended_at = reg['attended_at'] or ''
            try:
                t = datetime.fromisoformat(attended_at).strftime('%H:%M')
            except:
                t = attended_at
            answers = json.loads(reg.get('answers') or '{}')
            name = answers.get('full_name', f"{reg['first_name']} {reg.get('last_name', '')}")
            return web.json_response({
                'status': 'already',
                'name': name,
                'time': t
            }, headers={'Access-Control-Allow-Origin': '*'})

        now = datetime.now().isoformat()
        await db.execute(
            "UPDATE registrations SET attended=1, attended_at=? WHERE id=?",
            (now, reg['id'])
        )
        await db.commit()

        try:
            attended_time = datetime.now().strftime('%d.%m.%Y %H:%M')
            answers = json.loads(reg.get('answers') or '{}')
            name = answers.get('full_name', f"{reg['first_name']} {reg.get('last_name', '')}")
            mark_attended(reg['title_ru'], reg['event_date'], name, attended_time)
        except Exception as e:
            print(f"Sheets ошибка: {e}")

        answers = json.loads(reg.get('answers') or '{}')
        name = answers.get('full_name', f"{reg['first_name']} {reg.get('last_name', '')}")

        return web.json_response({
            'status': 'ok',
            'name': name,
            'event': reg['title_ru'],
            'date': reg['event_date']
        }, headers={'Access-Control-Allow-Origin': '*'})

async def manual_entry(request):
    data = await request.json()
    if data.get('token') != VOLUNTEER_TOKEN:
        return web.json_response({'error': 'unauthorized'}, status=401)

    name = data.get('name', '').strip()
    event_id = data.get('event_id')
    event_title = data.get('event_title', '')
    event_date = data.get('event_date', '')
    is_other = data.get('is_other', False)

    if not name or not event_title:
        return web.json_response({'ok': False, 'error': 'Заполните все поля'})

    now = datetime.now().strftime('%d.%m.%Y %H:%M')

    try:
        if is_other:
            ws = ensure_sheet('Другие мероприятия')
            headers = ws.row_values(1)
            if not headers:
                ws.append_row(['Имя', 'Мероприятие', 'Дата', 'Время входа'])
            ws.append_row([name, event_title, event_date, now])
        else:
            mark_attended(event_title, event_date, name, now)
            ws = ensure_sheet(f"{event_date} {event_title}"[:50])
            ws.append_row([name, now, '', 'РУЧНОЙ ВВОД', 'ДА', now])
    except Exception as e:
        print(f"Manual entry error: {e}")
        return web.json_response({'ok': False, 'error': 'Ошибка записи'}, headers={
            'Access-Control-Allow-Origin': '*'
        })

    return web.json_response({'ok': True}, headers={
        'Access-Control-Allow-Origin': '*'
    })

async def options_handler(request):
    return web.Response(headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, ngrok-skip-browser-warning'
    })

def create_app():
    app = web.Application()
    app.router.add_get('/api/events', get_events)
    app.router.add_post('/api/scan', scan_qr)
    app.router.add_post('/api/manual', manual_entry)
    app.router.add_route('OPTIONS', '/api/events', options_handler)
    app.router.add_route('OPTIONS', '/api/scan', options_handler)
    app.router.add_route('OPTIONS', '/api/manual', options_handler)
    return app
