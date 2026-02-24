"""
Food photo analysis via Claude Vision.
Downloads photo from Telegram, compresses with Pillow, sends to Claude Vision,
saves nutritional data to food_logs, responds with breakdown + daily summary.
"""

import base64
import io
import json
import logging
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic
from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import CLAUDE_API_KEY, TELEGRAM_CHAT_ID, IMAGE_MAX_SIZE, IMAGE_QUALITY, TZ
from bot.core.database import execute, fetchall, fetchone

logger = logging.getLogger(__name__)

CYPRUS_TZ = ZoneInfo(TZ)


def _get_meal_type(hour: int) -> tuple[str, str]:
    """Determine meal type and emoji based on Cyprus hour."""
    if 5 <= hour < 8:
        return "ранний завтрак", "\U0001f305"       # 🌅
    elif 8 <= hour < 11:
        return "завтрак", "\U0001f373"               # 🍳
    elif 11 <= hour < 14:
        return "обед", "\U0001f35d"                  # 🍝
    elif 14 <= hour < 17:
        return "перекус", "\U0001f34e"               # 🍎
    elif 17 <= hour < 21:
        return "ужин", "\U0001f37d\ufe0f"            # 🍽️
    elif 21 <= hour < 24:
        return "поздний ужин", "\U0001f319"          # 🌙
    else:  # 0-4
        return "ночной перекус", "\U0001f303"        # 🌃


def compress_image(file_bytes: bytes) -> tuple[bytes, str]:
    """Compress image to JPEG, max side IMAGE_MAX_SIZE px, quality IMAGE_QUALITY%.

    Returns (compressed_bytes, media_type).
    """
    img = Image.open(io.BytesIO(file_bytes))

    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')

    img.thumbnail((IMAGE_MAX_SIZE, IMAGE_MAX_SIZE), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=IMAGE_QUALITY, optimize=True)
    compressed = buf.getvalue()

    logger.info(
        "Image compressed: %dKB -> %dKB (%dx%d)",
        len(file_bytes) // 1024, len(compressed) // 1024,
        img.width, img.height,
    )
    return compressed, "image/jpeg"


async def analyze_food_photo(image_bytes: bytes, media_type: str, caption: str | None = None) -> dict:
    """Send image to Claude Vision for food analysis.

    Returns dict with dishes, total_calories, confidence, etc.
    """
    if not CLAUDE_API_KEY:
        return {"error": "Claude API key not configured"}

    image_b64 = base64.standard_b64encode(image_bytes).decode('utf-8')

    caption_hint = ""
    if caption:
        caption_hint = f"\nПользователь подписал фото: «{caption}»"

    prompt = (
        "Ты — нутрициолог-аналитик. Пользователь прислал фото еды.\n\n"
        "ЗАДАЧА:\n"
        "1. Определи все блюда/продукты на фото\n"
        "2. Оцени порцию (маленькая/средняя/большая)\n"
        "3. Оцени калории и БЖУ для каждого блюда\n\n"
        "ФОРМАТ ОТВЕТА — только JSON, без markdown:\n"
        "{\n"
        '  "is_food": true,\n'
        '  "dishes": [\n'
        '    {"name": "название", "portion": "средняя", "calories": 350, "protein": 25, "carbs": 30, "fat": 15}\n'
        '  ],\n'
        '  "total_calories": 350,\n'
        '  "confidence": "high",\n'
        '  "comment": "краткий комментарий на русском (1 предложение)"\n'
        "}\n\n"
        "confidence: high (чёткое фото, знакомое блюдо), medium (нечёткое/нестандартное), low (плохо видно).\n"
        'Если на фото НЕ еда: {"is_food": false}'
        f"{caption_hint}"
    )

    client = AsyncAnthropic(api_key=CLAUDE_API_KEY)
    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=600,
        temperature=0.3,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": prompt,
                },
            ],
        }],
    )

    raw_text = response.content[0].text.strip()

    # Extract JSON from response (Claude may wrap in ```json ... ```)
    if raw_text.startswith("```"):
        lines = raw_text.split('\n')
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            elif line.startswith("```") and in_block:
                break
            elif in_block:
                json_lines.append(line)
        raw_text = '\n'.join(json_lines)

    try:
        result = json.loads(raw_text)
        result['_raw'] = raw_text
        return result
    except json.JSONDecodeError:
        logger.error("Failed to parse Claude response: %s", raw_text[:200])
        return {"error": "Failed to parse response", "_raw": raw_text}


def save_food_log(timestamp: datetime, meal_type: str, dishes: list[dict],
                  confidence: str, raw_response: str) -> list[int]:
    """Save each dish as a row in food_logs. Returns list of inserted IDs."""
    ids = []
    for dish in dishes:
        cursor = execute(
            """INSERT INTO food_logs
               (timestamp, meal_type, dish_name, calories, protein_g, carbs_g, fat_g,
                confidence, source, raw_response)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'photo', ?)""",
            (
                timestamp.isoformat(),
                meal_type,
                dish.get('name', 'unknown'),
                dish.get('calories'),
                dish.get('protein'),
                dish.get('carbs'),
                dish.get('fat'),
                confidence,
                raw_response,
            ),
        )
        ids.append(cursor.lastrowid)
    return ids


def get_daily_calories_summary(date_str: str) -> tuple[int, int, str]:
    """Get today's calorie summary.

    Returns (total_calories, meal_count, formatted_summary).
    """
    rows = fetchall(
        """SELECT meal_type, dish_name, calories
           FROM food_logs
           WHERE date(timestamp) = ?
           ORDER BY timestamp""",
        (date_str,),
    )

    if not rows:
        return 0, 0, ""

    total = 0
    meals: dict[str, float] = {}
    for r in rows:
        cal = r['calories'] or 0
        total += cal
        mt = r['meal_type'] or 'другое'
        meals[mt] = meals.get(mt, 0) + cal

    parts = []
    for mt, cal in meals.items():
        parts.append(f"{mt} {cal:.0f}")

    summary = " + ".join(parts)
    return int(total), len(rows), summary


def format_food_response(analysis: dict, meal_type: str, meal_emoji: str,
                         daily_total: int, daily_count: int, daily_summary: str) -> str:
    """Format the bot response message."""
    dishes = analysis.get('dishes', [])
    confidence = analysis.get('confidence', 'medium')
    comment = analysis.get('comment', '')

    lines = [f"{meal_emoji} <b>{meal_type.capitalize()}</b> — распознано:"]

    for dish in dishes:
        cal = dish.get('calories', 0)
        name = dish.get('name', '?')
        portion = dish.get('portion', '')
        portion_str = f" ({portion})" if portion else ""
        lines.append(f"  \u2022 {name}{portion_str} — ~{cal} ккал")
        p = dish.get('protein', 0)
        c = dish.get('carbs', 0)
        f_ = dish.get('fat', 0)
        lines.append(f"    \u0411: {p}г | \u0416: {f_}г | \u0423: {c}г")

    total_cal = analysis.get('total_calories', 0)
    lines.append(f"\n\U0001f4ca \u0418\u0442\u043e\u0433\u043e: {total_cal} \u043a\u043a\u0430\u043b")

    if daily_count > 0:
        lines.append(
            f"\U0001f522 \u0421\u0435\u0433\u043e\u0434\u043d\u044f \u0432\u0441\u0435\u0433\u043e: "
            f"{daily_total} \u043a\u043a\u0430\u043b ({daily_count} "
            f"\u0437\u0430\u043f\u0438\u0441{'ь' if daily_count == 1 else 'ей' if daily_count >= 5 else 'и'})"
        )
        if daily_summary:
            lines.append(f"    {daily_summary}")

    conf_map = {"high": "\u2705 \u0432\u044b\u0441\u043e\u043a\u0430\u044f", "medium": "\u26a0\ufe0f \u0441\u0440\u0435\u0434\u043d\u044f\u044f", "low": "\u274c \u043d\u0438\u0437\u043a\u0430\u044f"}
    conf_str = conf_map.get(confidence, confidence)
    lines.append(f"\n\U0001f3af \u0422\u043e\u0447\u043d\u043e\u0441\u0442\u044c: {conf_str}")

    if comment:
        lines.append(f"\U0001f4ac {comment}")

    return '\n'.join(lines)


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages — analyze food via Claude Vision."""
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return

    if not CLAUDE_API_KEY:
        await update.message.reply_text("\u26a0\ufe0f Claude API \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d")
        return

    # Get the largest photo
    photo = update.message.photo[-1]
    caption = update.message.caption

    # Send "analyzing" indicator
    processing_msg = await update.message.reply_text("\U0001f50d \u0410\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u044e \u0444\u043e\u0442\u043e...")

    try:
        # Download photo
        file = await context.bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(suffix='.jpg') as tmp:
            await file.download_to_drive(tmp.name)
            tmp.seek(0)
            raw_bytes = tmp.read()

        # Compress
        compressed_bytes, media_type = compress_image(raw_bytes)

        # Analyze with Claude Vision
        analysis = await analyze_food_photo(compressed_bytes, media_type, caption)

        if analysis.get('error'):
            await processing_msg.edit_text(
                f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u0430\u043d\u0430\u043b\u0438\u0437\u0430: {analysis['error']}"
            )
            return

        if not analysis.get('is_food', True) is True:
            await processing_msg.edit_text(
                "\U0001f645 \u042d\u0442\u043e \u043d\u0435 \u043f\u043e\u0445\u043e\u0436\u0435 \u043d\u0430 \u0435\u0434\u0443. "
                "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0444\u043e\u0442\u043e \u0431\u043b\u044e\u0434\u0430 \u0434\u043b\u044f \u043f\u043e\u0434\u0441\u0447\u0451\u0442\u0430 \u043a\u0430\u043b\u043e\u0440\u0438\u0439."
            )
            return

        dishes = analysis.get('dishes', [])
        if not dishes:
            await processing_msg.edit_text(
                "\u26a0\ufe0f \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0431\u043b\u044e\u0434\u0430 \u043d\u0430 \u0444\u043e\u0442\u043e."
            )
            return

        # Determine meal type from Cyprus time
        now_cyprus = datetime.now(CYPRUS_TZ)
        meal_type, meal_emoji = _get_meal_type(now_cyprus.hour)

        # Save to DB
        raw_response = analysis.get('_raw', '')
        save_food_log(
            timestamp=now_cyprus,
            meal_type=meal_type,
            dishes=dishes,
            confidence=analysis.get('confidence', 'medium'),
            raw_response=raw_response,
        )

        # Get daily summary (including what we just saved)
        today_str = now_cyprus.strftime('%Y-%m-%d')
        daily_total, daily_count, daily_summary = get_daily_calories_summary(today_str)

        # Format response
        response = format_food_response(
            analysis, meal_type, meal_emoji,
            daily_total, daily_count, daily_summary,
        )

        await processing_msg.edit_text(response, parse_mode='HTML')

    except Exception as e:
        logger.error("Photo analysis error: %s", e, exc_info=True)
        await processing_msg.edit_text(
            f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u0430\u043d\u0430\u043b\u0438\u0437\u0435 \u0444\u043e\u0442\u043e: {e}"
        )


async def cmd_calories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /calories command — show today's food log and calorie summary."""
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return

    now_cyprus = datetime.now(CYPRUS_TZ)
    today_str = now_cyprus.strftime('%Y-%m-%d')

    rows = fetchall(
        """SELECT meal_type, dish_name, calories, protein_g, carbs_g, fat_g, timestamp
           FROM food_logs
           WHERE date(timestamp) = ?
           ORDER BY timestamp""",
        (today_str,),
    )

    if not rows:
        await update.message.reply_text(
            "\U0001f4cb \u0421\u0435\u0433\u043e\u0434\u043d\u044f \u0435\u0434\u0430 \u043d\u0435 \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u0430.\n\n"
            "\U0001f4f8 \u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0444\u043e\u0442\u043e \u0435\u0434\u044b \u0434\u043b\u044f \u043f\u043e\u0434\u0441\u0447\u0451\u0442\u0430 \u043a\u0430\u043b\u043e\u0440\u0438\u0439."
        )
        return

    total_cal = 0
    total_p = 0
    total_c = 0
    total_f = 0

    msg = f"<b>\U0001f4ca \u041a\u0410\u041b\u041e\u0420\u0418\u0418 \u0417\u0410 {now_cyprus.strftime('%d.%m.%Y')}</b>\n"

    current_meal = None
    for r in rows:
        mt = r['meal_type'] or 'другое'
        if mt != current_meal:
            current_meal = mt
            _, emoji = _get_meal_type(
                datetime.fromisoformat(r['timestamp']).hour if r['timestamp'] else 12
            )
            msg += f"\n{emoji} <b>{mt.capitalize()}</b>\n"

        cal = r['calories'] or 0
        p = r['protein_g'] or 0
        c = r['carbs_g'] or 0
        f_ = r['fat_g'] or 0
        total_cal += cal
        total_p += p
        total_c += c
        total_f += f_

        msg += f"  \u2022 {r['dish_name']} — {cal:.0f} ккал\n"

    msg += f"\n{'=' * 25}\n"
    msg += f"\U0001f525 <b>\u0418\u0442\u043e\u0433\u043e: {total_cal:.0f} \u043a\u043a\u0430\u043b</b>\n"
    msg += f"\u0411: {total_p:.0f}\u0433 | \u0416: {total_f:.0f}\u0433 | \u0423: {total_c:.0f}\u0433\n"
    msg += f"\U0001f4dd \u0417\u0430\u043f\u0438\u0441\u0435\u0439: {len(rows)}"

    await update.message.reply_text(msg, parse_mode='HTML')
