from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from languages import t

def language_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz")
        ]
    ])

def main_menu_keyboard(lang: str):
    return ReplyKeyboardMarkup(
        [
            [t(lang, "btn_events"), t(lang, "btn_my_registrations")],
            [t(lang, "btn_change_language")]
        ],
        resize_keyboard=True
    )