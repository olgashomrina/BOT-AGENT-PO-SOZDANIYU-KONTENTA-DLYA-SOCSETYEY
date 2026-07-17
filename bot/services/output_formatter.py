from __future__ import annotations

# WHY parse_mode="HTML" instead of MarkdownV2: MarkdownV2 treats ~18
# characters as special (_ * [ ] ( ) ~ ` > # + - = | { } . !) and a single
# unescaped one anywhere in AI-generated text (which can contain arbitrary
# punctuation — a dash in a CTA, parentheses, an exclamation mark) makes
# Telegram reject the whole message with a Bad Request. HTML only reserves
# three characters (< > &), which is far cheaper and safer to escape
# reliably for text we did not author ourselves. Trade-off: the *bold*/
# _italic_ markers the Phase 6 prompt asks the model to use will show up as
# literal asterisks/underscores rather than rendered emphasis — a cosmetic
# loss, not a robustness one, and preferable to messages silently failing
# to send.
PARSE_MODE = "HTML"

_HTML_ESCAPE_ORDER = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
)


def format_variant(text: str) -> str:
    escaped = text
    for char, replacement in _HTML_ESCAPE_ORDER:
        escaped = escaped.replace(char, replacement)
    return escaped
