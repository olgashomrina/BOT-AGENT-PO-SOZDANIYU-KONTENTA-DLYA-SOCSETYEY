from __future__ import annotations

STRINGS = {
    "start_greeting": (
        "你好！我是帮你创作社交媒体内容的机器人助手。\n\n"
        "很快我将学会把链接、语音消息和文字转换成可直接使用的 Telegram 和 "
        "VK 帖子。目前我还在开发中——这个命令暂时只是一个占位功能。\n\n"
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
    "error_limit_exceeded": (
        "您今天的每日请求额度已用完。新的额度将在明天开放。"
    ),
}
