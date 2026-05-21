import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
import uuid

ASSETS_DIR = "assets"
OUTPUT_DIR = "data/qr_codes"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_font(size):
    try:
        return ImageFont.truetype(f"{ASSETS_DIR}/Roboto.ttf", size)
    except:
        return ImageFont.load_default()
    
def draw_multiline(draw, text, x, y, font, fill, max_width):
    """Рисует текст с переносом по словам"""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    for i, line in enumerate(lines):
        draw.text((x, y + i * 22), line, font=font, fill=fill)

    return len(lines)  # возвращает сколько строк получилось

def load_font_bold(size):
    try:
        return ImageFont.truetype(f"{ASSETS_DIR}/Roboto-Bold.ttf", size)
    except:
        return ImageFont.load_default()

def generate_ticket(
    registration_id: int,
    event_title: str,
    event_date: str,
    event_location: str,
    participant_name: str,
    event_type: str = "offline"
) -> str:
    """Генерирует красивый билет с QR кодом и возвращает путь к файлу"""

    # Уникальный код
    unique_code = f"EVT-{registration_id:05d}"

    # Генерируем QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(unique_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#1a1a2e", back_color="white").convert("RGB")
    qr_img = qr_img.resize((280, 280), Image.LANCZOS)

    # Размеры билета
    W, H = 600, 520
    ticket = Image.new("RGB", (W, H), "#1a1a2e")
    draw = ImageDraw.Draw(ticket)

    # Верхняя полоса
    draw.rectangle([(0, 0), (W, 80)], fill="#16213e")

    # Логотип / название организации
    font_org = load_font_bold(18)
    draw.text((30, 18), "FRANCHISE COMMUNITY", font=font_org, fill="#e94560")
    font_type = load_font(14)
    event_label = "OFFLINE EVENT" if event_type == "offline" else "ONLINE EVENT"
    draw.text((30, 48), event_label, font=font_type, fill="#a8a8b3")

    # Название мероприятия
    font_title = load_font_bold(26)
    # Обрезаем если слишком длинное
    draw_multiline(draw, event_title, 30, 100, font_title, "#ffffff", 240)

    # Разделитель пунктирный
    for x in range(0, W, 12):
        draw.rectangle([(x, 148), (x + 6, 150)], fill="#a8a8b3")

    # QR код — справа
    ticket.paste(qr_img, (290, 160))

    # Инфо — слева
    font_label = load_font(13)
    font_value = load_font_bold(16)

    # Участник
    draw.text((30, 170), "УЧАСТНИК", font=font_label, fill="#a8a8b3")
    draw.text((30, 192), participant_name, font=font_value, fill="#ffffff")

    # Дата
    draw.text((30, 240), "ДАТА", font=font_label, fill="#a8a8b3")
    draw.text((30, 262), event_date, font=font_value, fill="#ffffff")

    # Место
    if event_type == "offline" and event_location:
        draw.text((30, 310), "МЕСТО", font=font_label, fill="#a8a8b3")
        draw_multiline(draw, event_location, 30, 332, font_value, "#ffffff", 240)

    # Код билета
    draw.text((30, 380), "КОД БИЛЕТА", font=font_label, fill="#a8a8b3")
    font_code = load_font_bold(22)
    draw.text((30, 402), unique_code, font=font_code, fill="#e94560")

    # Нижняя полоса
    draw.rectangle([(0, 460), (W, H)], fill="#16213e")
    font_footer = load_font(12)
    draw.text((30, 475), "Сохраните этот билет — предъявите на входе", font=font_footer, fill="#a8a8b3")

    # Угловые акценты
    draw.rectangle([(0, 0), (6, H)], fill="#e94560")

    # Сохраняем
    filename = f"{OUTPUT_DIR}/ticket_{unique_code}.png"
    ticket.save(filename, "PNG", quality=95)
    return filename, unique_code