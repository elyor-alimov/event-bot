TEXTS = {
    "ru": {
        "choose_language": "Выберите язык / Tilni tanlang:",
        "language_set": "Язык установлен: Русский 🇷🇺",
        "welcome": "👋 Привет, {name}!\nЯ бот для регистрации на мероприятия.",
        "main_menu": "Главное меню:",
        "btn_events": "📅 Мероприятия",
        "btn_my_registrations": "📋 Мои записи",
        "btn_change_language": "🌐 Язык",
        "events_empty": "Пока нет активных мероприятий.",
        "no_registrations": "У тебя пока нет записей.",
        "event_type_offline": "🏢 Офлайн",
        "event_type_online": "💻 Онлайн",
        "registration_confirmed": "✅ Ты зарегистрирован!\n\n📌 {event_name}\n📅 {event_date}\n📍 {event_location}",
        "online_reg_confirmed": "✅ Ты зарегистрирован!\n\n📌 {event_name}\n📅 {event_date}\n💻 Онлайн — ссылку пришлём накануне",
    },
    "uz": {
        "choose_language": "Выберите язык / Tilni tanlang:",
        "language_set": "Til o'rnatildi: O'zbek 🇺🇿",
        "welcome": "👋 Salom, {name}!\nMen tadbirlar uchun ro'yxatga olish botiman.",
        "main_menu": "Asosiy menyu:",
        "btn_events": "📅 Tadbirlar",
        "btn_my_registrations": "📋 Mening yozuvlarim",
        "btn_change_language": "🌐 Til",
        "events_empty": "Hozircha faol tadbirlar yo'q.",
        "no_registrations": "Sizda hali yozuvlar yo'q.",
        "event_type_offline": "🏢 Oflayn",
        "event_type_online": "💻 Onlayn",
        "registration_confirmed": "✅ Siz ro'yxatdan o'tdingiz!\n\n📌 {event_name}\n📅 {event_date}\n📍 {event_location}",
        "online_reg_confirmed": "✅ Siz ro'yxatdan o'tdingiz!\n\n📌 {event_name}\n📅 {event_date}\n💻 Onlayn — havola ertaga yuboriladi",
    }
}

def t(lang: str, key: str, **kwargs) -> str:
    """Получить текст на нужном языке"""
    text = TEXTS.get(lang, TEXTS["ru"]).get(key, key)
    return text.format(**kwargs) if kwargs else text