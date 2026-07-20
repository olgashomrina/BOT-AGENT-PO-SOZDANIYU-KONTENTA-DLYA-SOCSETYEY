from __future__ import annotations

STRINGS = {
    "start_greeting": (
        "Hi! I'm a bot assistant for creating social media content.\n\n"
        "Send me a link to an article, a voice message, or just plain text — "
        "and I'll prepare several ready-to-use post variants, separately for "
        "Telegram and for VK.\n\n"
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
    "transcript_preview": (
        "Here's what I heard in your voice message:\n\n{text}\n\n"
        "Is that correct?"
    ),
    "transcript_confirm_button": "Looks correct",
    "transcript_edit_button": "Edit",
    "transcript_edit_prompt": "Please send the corrected text.",
    "content_ready_stub": (
        "Text received! Post generation is still in development — soon "
        "I'll be able to turn it into ready-to-use variants for Telegram "
        "and VK."
    ),
    "refine_more_button": "More options",
    "refine_shorten_button": "Shorter",
    "error_refine_missing_context": (
        "I couldn't find the original text to refine — please send your "
        "material again."
    ),
    "channel_setup_instructions": (
        "To publish posts with one button, set up your channel:\n\n"
        "1. Add this bot as an administrator of your Telegram channel with "
        "permission to post messages.\n"
        "2. Forward any message from that channel here — I'll use it to "
        "identify the channel."
    ),
    "channel_setup_invalid_forward": (
        "This doesn't look like a message forwarded from a channel. Please "
        "forward any message from your Telegram channel."
    ),
    "channel_setup_bot_not_admin": (
        "I don't see administrator rights with posting permission in this "
        "channel. Make sure the bot is added as a channel administrator "
        "with the \"Post messages\" right enabled, then forward a message "
        "from the channel again."
    ),
    "channel_setup_confirmation": (
        "Done! The channel is set up — you can now publish posts to it "
        "with one button."
    ),
    "publish_to_channel_button": "Publish to channel",
    "publish_no_channel_configured": (
        "No channel is set up yet. Use the /channel command to connect "
        "your Telegram channel."
    ),
    "publish_success": "The post has been published to your channel.",
    "publish_failed": (
        "Couldn't publish the post to the channel — the bot may have lost "
        "administrator rights. Check its permissions and set up the "
        "channel again via /channel."
    ),
    "media_attached_confirmation": (
        "Got the photo/video! It will be attached to the next post you "
        "publish to your channel. To remove it, use the /clear_media "
        "command."
    ),
    "media_cleared_confirmation": "Attachment removed — the next post will publish without it.",
    "media_nothing_to_clear": "There's no photo or video attached right now.",
}
