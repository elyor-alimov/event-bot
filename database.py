import aiosqlite
import os
import json 

DB_PATH = "data/bot.db"

async def init_db():
    """Создаёт все таблицы если их нет"""
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:

        # Пользователи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                language TEXT DEFAULT 'ru',
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Мероприятия
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_ru TEXT,
                title_uz TEXT,
                description_ru TEXT,
                description_uz TEXT,
                event_date TEXT,
                location_ru TEXT,
                location_uz TEXT,
                event_type TEXT DEFAULT 'offline',
                online_link TEXT,
                is_active INTEGER DEFAULT 1,
                registration_open INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Регистрации
        await db.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                answers TEXT,
                qr_code TEXT,
                status TEXT DEFAULT 'registered',
                confirmed INTEGER DEFAULT 0,
                attended INTEGER DEFAULT 0,
                attended_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        """)

        # Кастомные вопросы для мероприятий
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                question_ru TEXT,
                question_uz TEXT,
                question_type TEXT DEFAULT 'text',
                options TEXT,
                is_required INTEGER DEFAULT 1,
                order_num INTEGER DEFAULT 0,
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        """)

        # Напоминания
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                hours_before INTEGER,
                content_ru TEXT,
                content_uz TEXT,
                media_url TEXT,
                media_type TEXT,
                is_sent INTEGER DEFAULT 0,
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        """)

        await db.commit()

# ─── Пользователи ───────────────────────────────────────────

async def get_or_create_user(telegram_id, first_name, last_name=None, username=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            user = await cursor.fetchone()

        if not user:
            await db.execute(
                """INSERT INTO users (telegram_id, first_name, last_name, username)
                   VALUES (?, ?, ?, ?)""",
                (telegram_id, first_name, last_name, username)
            )
            await db.commit()
            async with db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ) as cursor:
                user = await cursor.fetchone()

        return dict(user)

async def get_user(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            user = await cursor.fetchone()
            return dict(user) if user else None

async def set_user_language(telegram_id, language):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET language = ? WHERE telegram_id = ?",
            (language, telegram_id)
        )
        await db.commit()

async def set_user_admin(telegram_id, is_admin=True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_admin = ? WHERE telegram_id = ?",
            (1 if is_admin else 0, telegram_id)
        )
        await db.commit()

async def get_event_questions(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM event_questions WHERE event_id = ? ORDER BY order_num",
            (event_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            questions = []
            for row in rows:
                r = dict(row)
                opts = json.loads(r["options"]) if r["options"] else {"ru": [], "uz": []}
                questions.append({
                    "question_ru": r["question_ru"],
                    "question_uz": r["question_uz"],
                    "type": r["question_type"],
                    "options_ru": opts.get("ru", []),
                    "options_uz": opts.get("uz", [])
                })
            return questions
# ─── Мероприятия ────────────────────────────────────────────

async def get_active_events():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM events
               WHERE is_active = 1 AND registration_open = 1
               ORDER BY event_date ASC"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_event(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def create_event(data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO events
               (title_ru, title_uz, description_ru, description_uz,
                event_date, location_ru, location_uz, event_type, online_link)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["title_ru"], data["title_uz"],
                data["description_ru"], data["description_uz"],
                data["event_date"],
                data.get("location_ru"), data.get("location_uz"),
                data.get("event_type", "offline"),
                data.get("online_link")
            )
        )
        await db.commit()
        return cursor.lastrowid
    
# ─── Регистрации ─────────────────────────────────────────────

async def get_user_registrations(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT r.*, e.title_ru, e.title_uz, e.event_date, e.event_type
               FROM registrations r
               JOIN events e ON r.event_id = e.id
               JOIN users u ON r.user_id = u.id
               WHERE u.telegram_id = ?
               ORDER BY r.created_at DESC""",
            (telegram_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def create_registration(user_id, event_id, answers="{}"):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO registrations (user_id, event_id, answers)
               VALUES (?, ?, ?)""",
            (user_id, event_id, answers)
        )
        await db.commit()
        return cursor.lastrowid

async def check_already_registered(telegram_id, event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT r.id FROM registrations r
               JOIN users u ON r.user_id = u.id
               WHERE u.telegram_id = ? AND r.event_id = ?""",
            (telegram_id, event_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None
        
async def save_qr_code(registration_id, qr_code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE registrations SET qr_code = ? WHERE id = ?",
            (qr_code, registration_id)
        )
        await db.commit()

async def get_registration_by_user_and_event(user_id, event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT r.* FROM registrations r
               JOIN users u ON r.user_id = u.id
               WHERE u.telegram_id = ? AND r.event_id = ?""",
            (user_id, event_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None