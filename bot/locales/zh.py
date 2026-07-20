from __future__ import annotations

STRINGS = {
    "start_greeting": (
        "你好！我是帮你创作社交媒体内容的机器人助手。\n\n"
        "给我发送一个文章链接、一条语音消息，或者直接发送文字——我会分别为 "
        "Telegram 和 VK 准备好几个可直接使用的帖子方案。\n\n"
        "如需更改界面语言，请使用 /language 命令。"
    ),
    "language_prompt": "请选择界面语言：",
    "language_set_confirmation": "界面语言已切换为中文。",
    "error_ai_timeout": "生成服务目前响应比平时慢。请稍等几分钟后重试。",
    "error_rate_limit": "目前生成服务的请求过多。请稍等片刻后再试。",
    "error_ai_unavailable": (
        "无法连接到内容生成服务。我们已经知晓此类问题——请稍后再试。"
    ),
    "error_invalid_ai_response": "未能从 AI 模型获得有效响应。请重试一次。",
    "error_transcription": (
        "无法识别语音消息。请重新发送，或直接输入文字——同样有效。"
    ),
    "error_link_extraction": (
        "无法从该链接提取文本——页面可能受到保护无法自动读取，或暂时不可用。"
        "请尝试其他链接，或直接发送材料的文本内容。"
    ),
    "error_unexpected": (
        "我们这边出了点问题。我们已收到通知——请稍后重试。"
    ),
    "error_not_whitelisted": (
        "目前该机器人仅限受邀用户名单访问。如果您认为应当拥有访问权限，"
        "请联系机器人所有者。"
    ),
    "error_daily_limit_exceeded": (
        "您今天的每日请求额度已用完。新的额度将在明天开放。"
    ),
    "error_monthly_limit_exceeded": (
        "您本月的请求额度已用完。新的额度将在下个月开放。"
    ),
    "onboarding_capabilities": (
        "我能做什么：\n\n"
        "——接收文章链接、语音消息或直接发送的文字。\n"
        "——分别为 Telegram 和 VK 准备好几个帖子方案。\n"
        "——为帖子附加图片或视频——可以是您自己的，也可以是 AI 生成的。\n"
        "——一键将帖子直接发布到您的 Telegram 频道（/channel 命令）。\n\n"
        "命令列表：/start — 重新开始，/language — 切换界面语言，"
        "/channel — 设置频道，/clear_media — 移除已附加的媒体，"
        "/settov — 让机器人学习您的写作风格，/help — 再次显示此消息。"
    ),
    "onboarding_settov": (
        "希望帖子更贴近您自己的风格吗？发送 /settov 命令，并提交几篇您以前"
        "发布的帖子——机器人会记住它们，并在生成新文本时参考这些风格。"
    ),
    "onboarding_quick_start": (
        "快速开始：给我发送一个文章链接或一条语音消息——几秒钟后您就会收到"
        "可直接使用的帖子方案。"
    ),
    "transcript_preview": (
        "这是我在你的语音消息中听到的内容：\n\n{text}\n\n内容正确吗？"
    ),
    "transcript_confirm_button": "完全正确",
    "transcript_edit_button": "修改",
    "transcript_edit_prompt": "请发送修改后的文字。",
    "content_ready_stub": (
        "已收到文字！帖子生成功能仍在开发中——很快我就能把它变成可直接"
        "使用的 Telegram 和 VK 多个版本。"
    ),
    "refine_more_button": "换一个",
    "refine_shorten_button": "更简短",
    "error_refine_missing_context": (
        "找不到用于优化的原始文本——请重新发送材料。"
    ),
    "channel_setup_instructions": (
        "只需一键即可发布帖子，请先设置您的频道：\n\n"
        "1. 将此机器人添加为您 Telegram 频道的管理员，并授予发布消息的权限。\n"
        "2. 将该频道中的任意一条消息转发到这里——我会据此识别频道。"
    ),
    "channel_setup_invalid_forward": (
        "这看起来不是从频道转发的消息。请转发您 Telegram 频道中的任意一条消息。"
    ),
    "channel_setup_bot_not_admin": (
        "我在该频道中没有具备发布权限的管理员身份。请确认已将机器人添加为频道"
        "管理员并开启「发布消息」权限，然后重新转发该频道的一条消息。"
    ),
    "channel_setup_confirmation": (
        "完成！频道已设置好——现在您可以一键将帖子发布到该频道。"
    ),
    "publish_to_channel_button": "发布到频道",
    "publish_no_channel_configured": (
        "尚未设置频道。请使用 /channel 命令连接您的 Telegram 频道。"
    ),
    "publish_success": "帖子已发布到您的频道。",
    "publish_failed": (
        "未能将帖子发布到频道——机器人可能已失去管理员权限。请检查权限，并"
        "通过 /channel 重新设置频道。"
    ),
    "media_attached_confirmation": (
        "已收到图片/视频！它将附加到您下一次发布到频道的帖子中。如需移除，"
        "请使用 /clear_media 命令。"
    ),
    "media_cleared_confirmation": "已移除附件——下一个帖子将不带附件发布。",
    "media_nothing_to_clear": "当前没有已附加的图片或视频。",
    "generate_image_button": "🖼 AI 配图",
    "image_preview_caption": "AI 生成图片预览",
    "image_delivery_failed": "未能发送图片——请稍后重试。",
    "image_attached_confirmation": (
        "AI 生成的图片已准备好并已附加——它将用于您下一次发布到频道的帖子。"
        "如需移除，请使用 /clear_media 命令。"
    ),
    "settov_instructions": (
        "请发送几篇您自己以前发布的帖子——每条消息发一篇，纯文本形式。"
        "我会用它们作为参考，在生成新帖子时贴近您的风格。\n\n"
        "发送完所有示例后，请点击「完成」按钮。"
    ),
    "settov_done_button": "完成",
    "settov_example_saved": "示例已保存！可以再发一个，或点击「完成」。",
    "settov_example_too_long": (
        "这个示例太长了。请发送短一些的示例（不超过 2000 个字符）。"
    ),
    "settov_non_text_reprompt": (
        "请以纯文本消息发送示例，或者如果示例已经足够，请点击「完成」。"
    ),
    "settov_finished_confirmation": (
        "完成！已保存 {count} 个风格示例。生成新帖子时我会参考它们。"
    ),
}
