from __future__ import annotations

STRINGS = {
    "start_greeting": (
        "Hi! I'm a bot assistant for creating social media content.\n\n"
        "Soon I'll learn to turn links, voice messages and text into "
        "ready-to-use posts for Telegram and VK. I'm still in "
        "development — for now this command just works as a stub.\n\n"
        "To change the interface language, use the /language command."
    ),
    "language_prompt": "Choose your interface language:",
    "language_set_confirmation": "Interface language changed to English.",
    "error_ai_timeout": (
        "The generation service is responding slower than usual right "
        "now. Please try again in a couple of minutes."
    ),
    "error_rate_limit": (
        "There are too many requests to the generation service right now. "
        "Please wait a bit and try again."
    ),
    "error_ai_unavailable": (
        "We couldn't reach the content generation service. We're already "
        "aware of issues like this — please try again a bit later."
    ),
    "error_invalid_ai_response": (
        "We couldn't get a valid response from the AI model. Please try "
        "the request again."
    ),
    "error_transcription": (
        "We couldn't recognize the voice message. Please try sending it "
        "again, or type the text instead — that works too."
    ),
    "error_link_extraction": (
        "We couldn't extract the text from this link — the page might be "
        "protected from automatic reading or temporarily unavailable. Try "
        "another link or send the text of the material directly."
    ),
    "error_unexpected": (
        "Something went wrong on our side. We've already been notified — "
        "please try the request again a bit later."
    ),
    "error_not_whitelisted": (
        "Access to this bot is currently limited to a list of invited "
        "users. If you believe you should have access, contact the bot "
        "owner."
    ),
    "error_daily_limit_exceeded": (
        "You've used up your daily request limit for today. A new limit "
        "will be available tomorrow."
    ),
    "error_monthly_limit_exceeded": (
        "You've used up your monthly request limit. A new limit will be "
        "available next month."
    ),
    "help_text": (
        "Send me a link to an article, a voice message, or just plain "
        "text — and I'll help turn it into a ready-to-use post for "
        "Telegram and VK.\n\n"
        "Commands:\n"
        "/start — start over\n"
        "/language — change interface language\n"
        "/help — show this message"
    ),
    "content_stub_link": (
        "I see a link! Link processing is still in development — soon "
        "I'll be able to turn it into a ready post."
    ),
    "content_stub_voice": (
        "Got your voice message! Voice transcription is still in "
        "development — soon I'll be able to turn it into a ready post."
    ),
    "content_stub_text": (
        "Got your text! Post generation is still in development — soon "
        "I'll be able to turn it into ready-to-use variants."
    ),
}
