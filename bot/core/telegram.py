"""
Unified Telegram message sending.
"""

import logging

import aiohttp

from bot.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096


async def send_telegram_message(text: str, chat_id: str | None = None) -> bool:
    """Send a message to Telegram with HTML parse mode."""
    bot_token = TELEGRAM_BOT_TOKEN
    target_chat = chat_id or TELEGRAM_CHAT_ID

    if not bot_token or not target_chat:
        logger.warning("Telegram credentials not set")
        print(text)
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Split long messages
    messages = _split_message(text)

    for msg in messages:
        data = {
            'chat_id': target_chat,
            'text': msg,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Telegram send error %d: %s", resp.status, body)
                        return False
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            return False

    return True


def _split_message(text: str) -> list[str]:
    """Split message into chunks that fit Telegram's limit."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    parts = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            parts.append(text)
            break

        # Find a good split point (newline before limit)
        split_at = text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = MAX_MESSAGE_LENGTH

        parts.append(text[:split_at])
        text = text[split_at:].lstrip('\n')

    return parts
