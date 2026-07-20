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

# Instruction appended to the prompt for the "Короче" (shorten) refine button
# (Phase 7). Kept as a module-level constant rather than a magic string in
# the handler so tests and callers reference the same source of truth.
SHORTEN_INSTRUCTION = (
    "Rewrite it noticeably shorter than a typical post for this platform "
    "while keeping the core message and the call-to-action."
)


# Tone instruction (kept generic, platform-independent): the earlier prompt
# had no personality guidance at all, which produced flat, corporate-sounding
# drafts — this is the single biggest lever for making variants feel alive
# rather than interchangeable.
_TONE_INSTRUCTION = (
    "Write with genuine personality: be witty, a little playful, and use "
    "humor where it naturally fits the topic — avoid generic corporate "
    "phrasing and dry, safe summaries. It's fine to have an opinion or a "
    "surprising angle. Keep the humor tasteful and relevant to the source "
    "material, never forced."
)


def build_prompt(
    source_text: str,
    platform: Platform,
    content_language: str,
    extra_instruction: str | None = None,
) -> str:
    extra_line = f"{extra_instruction}\n" if extra_instruction else ""
    return (
        "You are a social media copywriter. Write ONE ready-to-publish social "
        "media post based on the source material below.\n"
        f"{_PLATFORM_INSTRUCTIONS[platform]}\n"
        f"{_TONE_INSTRUCTION}\n"
        f"Write the post in this language (ISO 639-1 code): {content_language}.\n"
        f"{extra_line}"
        "Return only the post text itself, without any preamble, quotes or "
        "explanation.\n\n"
        f"Source material:\n{source_text}"
    )


# Image models work best with English prompts regardless of what language
# the post itself is written in, so the instruction explicitly asks for an
# English-language description rather than mirroring content_language.
_IMAGE_PROMPT_INSTRUCTION = (
    "You are a visual prompt writer for an AI image generation model. Based "
    "on the social media post below (it may be written in any language), "
    "write ONE short, vivid, English-language visual description suitable "
    "as a direct prompt for an image generator. Describe concrete imagery, "
    "mood and style. Return only the prompt itself, without any preamble, "
    "quotes or explanation.\n\n"
    "Post:\n{post_text}"
)


async def generate_image_prompt(post_text: str) -> str:
    prompt = _IMAGE_PROMPT_INSTRUCTION.format(post_text=post_text)
    result = await ai_gateway.generate_text(prompt)
    return result.strip()


async def generate_variants(
    source_text: str,
    platform: Platform,
    content_language: str,
    count: int = 3,
    extra_instruction: str | None = None,
) -> list[str]:
    # Design call: call generate_text() `count` times with the same prompt
    # rather than asking the model for N variants in one response. Simpler
    # and more robust — a single-call "give me N options" instruction is
    # easy for a model to ignore or format inconsistently, whereas N
    # independent calls always yield N usable variants (relying on the
    # provider's own sampling randomness for variety).
    prompt = build_prompt(source_text, platform, content_language, extra_instruction)
    variants = []
    for _ in range(count):
        variant = await ai_gateway.generate_text(prompt, temperature=_VARIANT_TEMPERATURE)
        variants.append(variant)
    return variants
