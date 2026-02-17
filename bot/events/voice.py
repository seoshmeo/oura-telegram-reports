"""
Voice message transcription via OpenAI Whisper API.
"""

import logging
import tempfile
import os

from bot.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)


async def transcribe_voice(file_path: str) -> str | None:
    """
    Transcribe a voice message file using OpenAI Whisper API.

    Args:
        file_path: Path to the audio file (.ogg, .mp3, etc.)

    Returns:
        Transcribed text or None on failure
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set, voice transcription unavailable")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)

        with open(file_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru",
            )

        text = transcript.text.strip()
        logger.info("Voice transcribed: '%s'", text[:100])
        return text

    except Exception as e:
        logger.error("Whisper transcription failed: %s", e)
        return None


async def download_and_transcribe(bot, file_id: str) -> str | None:
    """
    Download voice file from Telegram and transcribe.

    Args:
        bot: telegram.Bot instance
        file_id: Telegram file_id for the voice message

    Returns:
        Transcribed text or None
    """
    try:
        file = await bot.get_file(file_id)

        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp:
            tmp_path = tmp.name

        await file.download_to_drive(tmp_path)
        logger.info("Voice file downloaded: %s", tmp_path)

        text = await transcribe_voice(tmp_path)

        # Clean up
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        return text

    except Exception as e:
        logger.error("Voice download/transcribe failed: %s", e)
        return None
