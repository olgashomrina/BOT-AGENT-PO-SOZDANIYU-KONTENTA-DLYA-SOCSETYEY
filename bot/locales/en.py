from __future__ import annotations

STRINGS = {
    "start_greeting": (
        "Hi! I'm a bot assistant for creating social media content and "
        "for your personal website — I write in your own unique style, "
        "in Russian, English, Chinese, and Vietnamese.\n\n"
        "Send me a link to an article, a voice message, text, or "
        "describe the image you want — and I'll prepare ready-to-use "
        "post variants for Telegram and VK.\n\n"
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
    "error_out_of_budget": (
        "The generation service is temporarily unavailable for technical "
        "reasons. The owner has already been notified — this is usually "
        "resolved within a few hours. Please try again later."
    ),
    "error_voice_too_long": (
        "That voice message is longer than {limit_minutes} min — I don't "
        "transcribe those. Please record a shorter one or send text instead."
    ),
    "error_daily_image_limit": (
        "No images left for today — the limit is {limit} per day. Post text "
        "still works, and images open up again tomorrow."
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
    "onboarding_capabilities": (
        "What I can do:\n\n"
        "— Accept a link to an article, a voice message, or plain "
        "text — and prepare several post variants, separately for "
        "Telegram and for VK, written in your own individual style.\n"
        "— Write in Russian, English, Chinese, and Vietnamese.\n"
        "— Generate an image from your description — on its own or as "
        "an addition to a post.\n"
        "— Publish a post straight to your Telegram channel with one "
        "button (the /channel command).\n"
        "— Pull and update the services card on your personal website "
        "right from the chat (the /site command).\n\n"
        "Commands: /start — start over, /language — change interface "
        "language, /channel — set up a channel, /site — work with the "
        "website, /clear_media — remove the attached media, /settov — "
        "teach the bot your writing style, /help — show this message "
        "again."
    ),
    "onboarding_settov": (
        "Want posts that sound like you? Send the /settov command and "
        "submit a few of your past posts — the bot will remember them and "
        "use them as a reference when generating new texts."
    ),
    "onboarding_quick_start": (
        "Quick start: send me a link to an article or a voice message — "
        "and in a few seconds you'll get ready-to-use post variants."
    ),
    "start_button_label": "Start",
    "command_start_description": "Start the bot",
    "menu_intro": "What shall we do next?",
    "menu_capabilities_button": "What I can do",
    "menu_cta_button": "Create a post now",
    "menu_news_digest_button": "Gather a fresh news digest",
    "menu_digest_write_topic_button": "Write the topic you're interested in",
    "menu_digest_change_topic_button": "Change topic",
    "digest_prompt_no_topic": (
        "To collect a digest, first tell me a topic you're interested in."
    ),
    "digest_change_topic_prompt": "Want to collect a digest on a different topic?",
    "digest_topic_input_prompt": "Write the topic to collect a digest for:",
    "digest_topic_input_placeholder": "For example: psychology",
    "digest_topic_saved": "Topic saved: \"{topic}\". Collecting the digest...",
    "digest_title": "📋 Digest on \"{topic}\" for {date}",
    "digest_section_news": "📰 In the news",
    "digest_section_papers": "🔬 Scientific papers",
    "digest_section_methods": "💡 New methods",
    "digest_empty_result": (
        "Nothing found on \"{topic}\" today. Try another topic or check "
        "back later."
    ),
    "menu_text_generation_button": "Text generation",
    "menu_text_generation_hint": (
        "Send me a link to an article, a voice message, or text — "
        "I'll prepare post variants for Telegram and VK."
    ),
    "menu_photo_generation_button": "Photo generation",
    "post_length_button": "📏 Post length: {value}",
    "post_length_prompt": (
        "How long should your posts be? Every option is guaranteed to fit a "
        "Telegram post — even when there is an image attached."
    ),
    "post_length_saved": "Done. Post length: {value}.",
    "post_length_short": "Short",
    "post_length_medium": "Medium",
    "post_length_expanded": "Detailed",
    "photo_gen_prompt": "Describe the image you want — I'll generate it using AI.",
    "photo_gen_ready": (
        "The image is ready! Now send me text, a link to an article, "
        "or a voice message — I'll prepare a post with this image."
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
    "generate_image_button": "🖼 AI image",
    "image_preview_caption": "AI-generated image preview",
    "image_delivery_failed": "Couldn't send the image — please try again in a moment.",
    "image_attached_confirmation": (
        "The AI-generated image is ready and attached — it will be used "
        "for the next post you publish to your channel. To remove it, use "
        "the /clear_media command."
    ),
    "image_upgrade_button": "🎨 Make it more realistic (~15₽)",
    "image_upgraded_button": "✅ Done",
    "image_upgraded_caption": "✨ More realistic version",
    "settov_instructions": (
        "Send me a few of your own past posts — one per message, plain "
        "text. I'll use them as a reference for your style when generating "
        "new posts.\n\n"
        "Once you've sent all the examples, tap the \"Done\" button."
    ),
    "settov_done_button": "Done",
    "settov_example_saved": "Example saved! Send another one or tap \"Done\".",
    "settov_example_too_long": (
        "This example is too long. Please send a shorter one (up to 2000 "
        "characters)."
    ),
    "settov_non_text_reprompt": (
        "Please send the example as a plain text message, or tap \"Done\" "
        "if you have enough examples."
    ),
    "settov_finished_confirmation": (
        "Done! Saved style examples: {count}. I'll take them into account "
        "when generating new posts."
    ),
    "site_menu_intro": (
        "Here you can open your site or pull the service card content for editing."
    ),
    "open_site_button": "MY SITE",
    "pull_from_site_button": "Pull the 'Services' card",
    "site_push_button": "Push to site",
    "site_pull_empty": (
        "Nothing has been pushed to this card on the site yet — use the "
        "'Push to site' button first."
    ),
    "site_push_success": "Done! The card on the site has been updated.",
    "site_push_photo_failed": "Couldn't download the photo for the site — please try again in a moment.",
    "authorpost_button": "✍️ WRITE MY AUTHORED POST",
    "authorpost_digest_expired": (
        "This digest has expired — collect a fresh one and the authored "
        "post button will work again."
    ),
    "authorpost_choose_item": "Which digest item should the post be about?",
    "authorpost_item_chosen": "Great, going with: {item}",
    "authorpost_next_button": "I'll help you write it — tap to continue",
    "authorpost_saved_examples_intro": (
        "I already know your voice — saved examples: {count}. Write from "
        "those, or upload fresh ones?"
    ),
    "authorpost_use_saved_button": "Write now",
    "authorpost_new_samples_button": "Upload new examples",
    "authorpost_samples_cleared": "Old examples deleted. Send the new ones.",
    "authorpost_samples_prompt": (
        "Paste examples of your own posts — at least {required}. Send them "
        "one after another, one per message, as plain text. I'll read your "
        "personal writing voice from them."
    ),
    "authorpost_samples_progress": "Accepted {count} of {required}.",
    "authorpost_samples_enough": (
        "Accepted {count} of {required} ✅ That's enough. Send more for "
        "accuracy, or tap the button."
    ),
    "authorpost_samples_done_button": "✒ Write the post on the chosen topic",
    "style_read_summary": (
        "I've read your style ✅\n\n"
        "How you write:\n"
        "{summary}\n\n"
        "I'll write the same way."
    ),
    "style_button_own_topic": "✍ Authored post on my own topic",
    "style_button_fresh_digest": "📰 Post from a fresh digest",
    "style_own_topic_prompt": (
        "Send me a topic or a text — I'll turn it into a post in your voice. "
        "A link or a voice message works too."
    ),
    "authorpost_sample_too_long": (
        "This example is too long. Please send a shorter one (up to 2000 "
        "characters)."
    ),
    "authorpost_sample_non_text": (
        "Please send the example as a plain text message."
    ),
    "authorpost_choose_platform": "Where are we posting?",
    "authorpost_platform_telegram_button": "Telegram",
    "authorpost_platform_vk_button": "VK",
    "authorpost_platform_both_button": "Both",
    "authorpost_generating": "Writing an authored post in your voice...",
    "package_button": "📦 Social media pack",
    "package_intro": (
        "Ready-made packs for Instagram, YouTube Shorts and Facebook.\n\n"
        "The boxed text copies with one tap — paste it into the platform's app "
        "and publish it yourself. The bot never publishes on your behalf and "
        "never asks for access to your accounts."
    ),
    "package_title_label": "Title:",
    "package_body_label": "Description:",
    "package_media_spec": "📐 Video: {aspect}, {resolution}, {seconds}",
    "package_note_links_not_clickable": (
        "🔗 Links aren't clickable in captions here — put the link in your "
        "profile bio instead (found in the text: {count})"
    ),
    "package_note_caption_truncated": (
        "✂️ Text trimmed to the platform limit — {limit} characters"
    ),
    "package_note_hashtags_trimmed": (
        "#️⃣ Hashtags cut down to {max} — that's what fits this platform"
    ),
    "package_note_preview": (
        "👀 Only the first {preview} characters show before \"more\" — keep the "
        "hook inside them"
    ),
    "package_note_ai_disclosure": (
        "🤖 When uploading, mark the video as AI-generated (on YouTube this is "
        "mandatory)"
    ),
    "double_consent_accept_button": "Agreed, build my double",
    "double_donors_done_button": "Done, build the double",
    "double_add_donors_button": "Add circles",
    "double_delete_button": "Delete double",
    "double_delete_confirm_button": "Yes, delete everything",
    "double_consent_text": (
        "I'll build your double for video circles.\n\n"
        "I'll take your circles and learn your face, expressions and voice from them. "
        "Stored on my side, and one button deletes it all whenever you want."
    ),
    "double_donors_invite": (
        "Forward me {minimum}-5 of your longer circles — the ones you like yourself.\n"
        "Send them one by one, I'll keep count."
    ),
    "double_donor_saved": "Got {collected} of {minimum}.",
    "double_donor_too_short": (
        "This circle is shorter than {minimum} seconds — too short to carry speech. "
        "Send a longer one."
    ),
    "double_expected_video_note": "I need a circle — record or forward a video message.",
    "double_status_text": "Your double: {donors} donor circles, voice — {voice}.",
    "double_voice_ready": "ready",
    "double_voice_missing": "not built yet",
    "double_need_more_donors": "I need at least {minimum} circles. Send more.",
    "double_voice_building": "Building the voice, this takes about a minute…",
    "double_voice_failed": (
        "Couldn't build the voice. Try again a bit later — "
        "your circles are saved, no need to resend them."
    ),
    "double_ready": "Double ready: built on {donors} circles, voice created.",
    "double_delete_confirm_text": (
        "This deletes the circles, the transcripts and the voice. "
        "It can't be undone — the double would have to be built from scratch."
    ),
    "double_deleted": "The double and all of its data are deleted.",
    "menu_my_double_button": "🎭 My double",
    "double_status_full": (
        "Your double: face — {face}, looks — {looks}, active — {active}."
    ),
    "double_face_present": "uploaded",
    "double_face_missing": "not uploaded",
    "double_look_none": "none",
    "double_speak_button": "🎤 Give a speech",
    "double_looks_button": "🖼 Looks",
    "double_face_button": "📸 Replace face",
    "double_voice_button": "🎙 Voice",
    "face_invite": (
        "Send one sharp frontal photo of your face: head and shoulders filling "
        "the frame, calm expression, eyes to the camera.\n\n"
        "Every look is built from this face, so the sharper it is, the more "
        "the circles will look like you."
    ),
    "face_saved": "Face saved. Now you can build looks.",
    "face_expected_photo": "I need a photo — send it as a picture, not a file.",
    "looks_title": "Looks: {count}. Active — {active}.",
    "looks_add_photo_button": "Send a picture",
    "looks_add_prompt_button": "Describe it",
    "looks_upload_invite": (
        "Send the look as a picture.\n\n"
        "It matters: close-up, head and shoulders filling the frame. In a wide "
        "shot the face takes a fifth of the frame and the circle comes out blurry."
    ),
    "looks_prompt_invite": (
        "Describe the clothes, the place and the light — for example: «white "
        "shirt, dark background, soft side light».\n\n"
        "I'll build the look from your face for 4 ₽ and show it before any filming."
    ),
    "looks_hair_warning": (
        "A warning: when you ask to change the hair, the model happily changes "
        "the face too. I'll do it, but look at the result closely."
    ),
    "looks_need_face": "Send a photo of your face first — the look is built from it.",
    "looks_building": "Building the look, under a minute…",
    "looks_failed": "Couldn't build the look. Try again or send a ready picture.",
    "looks_saved": "Look saved.",
    "looks_activated": "Active look changed.",
    "look_activate_button": "Make active",
    "look_delete_button": "Delete look",
    "look_deleted": "Look deleted.",
    "speech_invite": (
        "Write the text of your speech or record it as a voice message.\n\n"
        "A voice message goes into the circle as is — in your real voice."
    ),
    "speech_text_received": "Got the text:\n\n{text}",
    "speech_voice_as_is_button": "Voice it as is",
    "speech_script_button": "Make it a script",
    "speech_rewrite_button": "Rewrite",
    "speech_cancel_button": "Cancel",
    "speech_cancelled": "Cancelled. Nothing was spent.",
    "speech_script_failed": "Couldn't write the script. Your text is saved.",
    "speech_prompter": (
        "Voice synthesis is off for now, so here's a prompter — read this out "
        "as a voice message and I'll film the circle:\n\n{text}"
    ),
    "speech_voice_failed": (
        "Couldn't voice it. The text is saved — try again or record a voice message."
    ),
    "speech_voiced": "Here's the audio, {seconds} seconds. Listen before filming.",
    "speech_render_button": "Film the circle",
    "speech_revoice_button": "Record again",
    "speech_back_to_text_button": "Back to the text",
    "speech_too_long": (
        "That's longer than {limit} seconds, and a circle can't be. Shorten the speech."
    ),
    "speech_look_screen": "I'll film with this look: {title}",
    "speech_render_with_look_button": "Film with this look",
    "speech_other_look_button": "Another look",
    "speech_rendering": (
        "Filming. It takes a few minutes — I'll send it when it's ready, "
        "no need to wait in the chat."
    ),
    "speech_ready": "The circle is ready. Take a look and decide about publishing.",
    "speech_rewrite_text_button": "Rewrite the text",
    "speech_drop_button": "Delete",
    "speech_failed": (
        "Filming failed. The text and the audio are saved — a retry costs "
        "only the filming."
    ),
    "speech_retry_button": "Retry",
    "speech_limit_exceeded": (
        "You're out of filming seconds this month: {left} left. "
        "The limit resets on the first."
    ),
    "speech_need_face": "Upload the double's face first — there's nothing to film without it.",
    "speech_need_look": "Add at least one look first.",
    "speech_expected_input": "I'm waiting for text or a voice message.",
}
