import gspread
from google.oauth2.service_account import Credentials
import os
import base64
import json

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '1gqtPemSKugRL4Esu02GTImznm_fBaekUwK_i1SHNrUg')

def get_client():
    creds_b64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')
    if creds_b64:
        creds_dict = json.loads(base64.b64decode(creds_b64).decode('utf-8'))
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)

def get_spreadsheet():
    client = get_client()
    return client.open_by_key(SPREADSHEET_ID)

def ensure_sheet(title):
    """Создаёт лист если его нет"""
    ss = get_spreadsheet()
    titles = [ws.title for ws in ss.worksheets()]
    if title not in titles:
        ss.add_worksheet(title=title, rows=500, cols=20)
    return ss.worksheet(title)

def setup_sheets():
    """Создаёт все нужные листы при первом запуске"""
    ss = get_spreadsheet()
    existing = [ws.title for ws in ss.worksheets()]

    # Лист мероприятий
    if "Мероприятия" not in existing:
        ws = ss.add_worksheet("Мероприятия", rows=500, cols=20)
        ws.append_row([
            "ID", "Название RU", "Название UZ",
            "Описание RU", "Описание UZ",
            "Дата", "Тип", "Адрес RU", "Адрес UZ",
            "Фото (ссылка)", "Активно", "Регистрация открыта"
        ])

    # Лист вопросов
    if "Вопросы" not in existing:
        ws = ss.add_worksheet("Вопросы", rows=500, cols=10)
        ws.append_row([
            "ID мероприятия", "Вопрос RU", "Вопрос UZ",
            "Тип (text/buttons)", "Варианты (через запятую)"
        ])

    # Лист напоминаний
    if "Напоминания" not in existing:
        ws = ss.add_worksheet("Напоминания", rows=500, cols=10)
        ws.append_row([
            "ID мероприятия", "За сколько часов",
            "Текст RU", "Текст UZ",
            "Файл (ссылка)", "Тип файла", "Отправлено"
        ])

    # Лист рассылок
    if "Рассылки" not in existing:
        ws = ss.add_worksheet("Рассылки", rows=500, cols=10)
        ws.append_row([
            "Кому", "ID мероприятия", "Текст RU", "Текст UZ",
            "Файл (ссылка)", "Тип файла", "Статус", "Когда отправить"
        ])

    print("Листы в Google Sheets готовы ✅")

def sync_events_to_db():
    """Читает мероприятия из Sheets и возвращает список"""
    ws = ensure_sheet("Мероприятия")
    rows = ws.get_all_records()
    return rows

def convert_drive_link(url):
    """Конвертирует обычную ссылку Drive в прямую ссылку на файл"""
    if not url:
        return None
    if "drive.google.com/file/d/" in url:
        file_id = url.split("/file/d/")[1].split("/")[0]
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return url

def mark_reminder_sent(row_index):
    """Отмечает напоминание как отправленное"""
    ws = ensure_sheet("Напоминания")
    ws.update_cell(row_index + 2, 7, "ДА")

def get_reminders():
    """Возвращает все напоминания"""
    ws = ensure_sheet("Напоминания")
    rows = ws.get_all_records()
    return [(i, r) for i, r in enumerate(rows)]

def get_blasts():
    """Возвращает рассылки готовые к отправке"""
    ws = ensure_sheet("Рассылки")
    rows = ws.get_all_records()
    return [(i, r) for i, r in enumerate(rows) if r.get("Статус") == "ГОТОВО"]

def mark_blast_sent(row_index):
    """Отмечает рассылку как отправленную"""
    ws = ensure_sheet("Рассылки")
    ws.update_cell(row_index + 2, 7, "ОТПРАВЛЕНО")

def add_attendance_sheet(event_title, event_date):
    sheet_name = f"{event_date} {event_title}"[:50]
    ws = ensure_sheet(sheet_name)
    headers = ws.row_values(1)
    if not headers:
        ws.append_row([
            "Имя", "Дата регистрации",
            "Подтвердил", "Пришёл", "Время входа",
            "Ответ 1", "Ответ 2", "Ответ 3"
        ])
    return ws

def mark_attended(event_title, event_date, full_name, attended_at):
    """Отмечает участника как пришедшего"""
    sheet_name = f"{event_date} {event_title}"[:50]
    ws = ensure_sheet(sheet_name)
    data = ws.get_all_values()
    for i, row in enumerate(data[1:], start=2):
        if row and row[0] == full_name:
            ws.update_cell(i, 5, "ДА")
            ws.update_cell(i, 6, attended_at)
            return True
    return False

def add_registration_to_sheet(event_title, event_date, full_name, answers, registered_at):
    ws = add_attendance_sheet(event_title, event_date)
    parsed = json.loads(answers) if isinstance(answers, str) else answers
    parsed.pop("full_name", None)

    # Максимум 3 ответа в отдельных колонках
    answer_values = list(parsed.values())[:3]
    while len(answer_values) < 3:
        answer_values.append("")

    ws.append_row([full_name, registered_at, "", "", ""] + answer_values)

def get_questions_for_event(sheet_id):
    try:
        ws = ensure_sheet("Вопросы")
        rows = ws.get_all_records()
        questions = []
        for row in rows:
            if str(row.get("ID мероприятия", "")).strip() == str(sheet_id):
                questions.append({
                    "question_ru": row.get("Вопрос RU", ""),
                    "question_uz": row.get("Вопрос UZ", ""),
                    "type": row.get("Тип (text/buttons)", "text").strip(),
                    "options_ru": [o.strip() for o in row.get("Варианты (через запятую) RU", "").split(",") if o.strip()],
                    "options_uz": [o.strip() for o in row.get("Варианты (через запятую) UZ", "").split(",") if o.strip()]
                })
        return questions
    except Exception as e:
        print(f"Ошибка чтения вопросов: {e}")
        return []