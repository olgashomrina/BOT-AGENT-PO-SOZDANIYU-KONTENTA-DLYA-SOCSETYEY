from __future__ import annotations

from typing import Literal

from bot.services import ai_gateway

Platform = Literal["telegram", "vk"]

# Fixed moderately-high temperature for all variant calls: high enough that
# repeated calls with the byte-identical prompt actually diverge (a low or
# default temperature risks near-identical "variants"), but not so high that
# posts drift into incoherence. Not exposed via Settings for MVP-1 — a single
# constant is enough until real usage shows it needs tuning.
_VARIANT_TEMPERATURE = 0.9

# Platform-specific style guidance baked into the prompt itself (Plan.md
# Phase 6 / speca.md §3). Written in English so it stays unambiguous
# regardless of content_language — the model is explicitly told which
# language to write the POST in via a separate instruction line.
_PLATFORM_INSTRUCTIONS: dict[Platform, str] = {
    "telegram": (
        "Platform: Telegram post. Keep it short and casual (a few sentences), "
        "use light Markdown-style emphasis (*bold*/_italic_) sparingly, include "
        "a couple of fitting emoji, and end with a short, punchy call-to-action."
    ),
    "vk": (
        "Platform: VK (VKontakte) post. You may write a bit longer than for "
        "Telegram, open with a strong hook in the very first line, use emoji "
        "naturally throughout, and close with a clear call-to-action."
    ),
}


def build_prompt(source_text: str, platform: Platform, content_language: str) -> str:
    return (
        "You are a social media copywriter. Write ONE ready-to-publish social "
        "media post based on the source material below.\n"
        f"{_PLATFORM_INSTRUCTIONS[platform]}\n"
        f"Write the post in this language (ISO 639-1 code): {content_language}.\n"
        "Return only the post text itself, without any preamble, quotes or "
        "explanation.\n\n"
        f"Source material:\n{source_text}"
    )


async def generate_variants(
    source_text: str,
    platform: Platform,
    content_language: str,
    count: int = 3,
) -> list[str]:
    # Design call: call generate_text() `count` times with the same prompt
    # rather than asking the model for N variants in one response. Simpler
    # and more robust — a single-call "give me N options" instruction is
    # easy for a model to ignore or format inconsistently, whereas N
    # independent calls always yield N usable variants (relying on the
    # provider's own sampling randomness for variety).
    prompt = build_prompt(source_text, platform, content_language)
    variants = []
    for _ in range(count):
        variant = await ai_gateway.generate_text(prompt, temperature=_VARIANT_TEMPERATURE)
        variants.append(variant)
    return variants
