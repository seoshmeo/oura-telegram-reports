"""
Telegram keyboard layouts.
"""

from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup

# Button text constants (used for matching in handler)
BTN_LISINOPRIL = "\U0001f48a \u041b\u0438\u0437\u0438\u043d\u043e\u043f\u0440\u0438\u043b"
BTN_GLUCOPHAGE = "\U0001f48a \u0413\u043b\u044e\u043a\u043e\u0444\u0430\u0436"
BTN_BP = "\U0001fa78 \u0414\u0430\u0432\u043b\u0435\u043d\u0438\u0435"
BTN_SUGAR = "\U0001fa78 \u0421\u0430\u0445\u0430\u0440"
BTN_WEIGHT = "\u2696\ufe0f \u0412\u0435\u0441"
BTN_COFFEE = "\u2615 \u041a\u043e\u0444\u0435"
BTN_WALK = "\U0001f6b6 \u041f\u0440\u043e\u0433\u0443\u043b\u043a\u0430"
BTN_WORKOUT = "\U0001f3cb\ufe0f \u0422\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0430"
BTN_HOOKAH = "\U0001f4a8 \u041a\u0430\u043b\u044c\u044f\u043d"
BTN_ALCOHOL = "\U0001f37a \u0410\u043b\u043a\u043e\u0433\u043e\u043b\u044c"
BTN_STRESS = "\U0001f624 \u0421\u0442\u0440\u0435\u0441\u0441"
BTN_SUPPLEMENT = "\U0001f48a \u0414\u043e\u0431\u0430\u0432\u043a\u0438"
BTN_LATE_MEAL = "\U0001f374 \u041f\u043e\u0437\u0434\u043d\u044f\u044f \u0435\u0434\u0430"

# Command buttons
BTN_EVENTS = "\U0001f4cb \u0421\u043e\u0431\u044b\u0442\u0438\u044f"
BTN_MEDS = "\U0001f48a \u041b\u0435\u043a\u0430\u0440\u0441\u0442\u0432\u0430"
BTN_MEASUREMENTS = "\U0001f4ca \u0418\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u044f"

# Sets for matching
COMMAND_BUTTONS = {BTN_EVENTS, BTN_MEDS, BTN_MEASUREMENTS}
AWAITING_BUTTONS = {BTN_BP, BTN_SUGAR, BTN_WEIGHT}

# Main persistent keyboard
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_LISINOPRIL, BTN_GLUCOPHAGE],
        [BTN_BP, BTN_SUGAR, BTN_WEIGHT],
        [BTN_COFFEE, BTN_WALK, BTN_WORKOUT],
        [BTN_HOOKAH, BTN_ALCOHOL, BTN_STRESS],
        [BTN_EVENTS, BTN_MEDS, BTN_MEASUREMENTS],
    ],
    resize_keyboard=True,
    input_field_placeholder="\u0421\u043e\u0431\u044b\u0442\u0438\u0435 \u0438\u043b\u0438 \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u0435...",
)


def cancel_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard with cancel button after recording an event."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u274c \u041e\u0442\u043c\u0435\u043d\u0438\u0442\u044c", callback_data=f"cancel:{event_id}")]
    ])
