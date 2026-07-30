"""Готовит пост к ручной публикации в Instagram, YouTube Shorts и Facebook.

WHY этот модуль не публикует ничего сам (socseti.md, разбор 2026-07-29):
доставка на внешние площадки тянет за собой App Review (2–4 недели), хранение
чужих OAuth-токенов, вопрос доступности API Meta с российского IP и чужую
юридическую ответственность за содержание поста (ФЗ-72). Ни одна из этих
сложностей не нужна, чтобы дать пользователю ценность: подготовка ассета и
доставка — разные задачи, и первая полностью решается локально.

Отсюда жёсткое ограничение, которое надо сохранять при доработках: **здесь нет
и не должно появиться ни одного сетевого вызова, ни одного токена и ни одного
обращения к ИИ**. Всё, что делает модуль, — детерминированное преобразование
уже утверждённого пользователем текста. Это делает его целиком тестируемым
без моков и бесплатным по расходу.

Тексты подсказок здесь не собираются: заметки и спека медиа возвращаются
ключами локализации (`Note.key` + параметры), а строку подставляет хендлер
через `get_string`. Так модуль остаётся независимым от языка интерфейса.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ExternalPlatform = Literal["instagram", "youtube_shorts", "facebook"]

MEDIA_SPEC_KEY = "package_media_spec"


@dataclass(frozen=True)
class Note:
    """Подсказка пользователю: ключ локализации плюс параметры подстановки."""

    key: str
    params: dict[str, object]


@dataclass(frozen=True)
class PlatformProfile:
    display_name: str
    # Лимит подписи/описания. Для Instagram он включает в себя хештеги —
    # см. _fit_caption(), где под них резервируется место.
    caption_limit: int
    # Сколько символов подписи видно до «ещё»: определяет, где должен стоять
    # крючок. None — если на площадке крючок несёт не подпись (у Shorts эту
    # роль играет заголовок, и подсказка про подпись только путала бы).
    preview_limit: int | None
    hashtag_max: int
    links_clickable: bool
    # None означает, что у площадки нет отдельного поля заголовка.
    title_limit: int | None
    video_aspect: str
    video_resolution: str
    video_seconds: str


# Данные профилей — из разведки в socseti.md (разделы 1 и 5). Значения,
# помеченные там как непроверенные, здесь намеренно взяты консервативно:
# лучше подсказать пользователю более узкую рамку, чем более широкую.
PROFILES: dict[str, PlatformProfile] = {
    "instagram": PlatformProfile(
        display_name="Instagram Reels",
        caption_limit=2200,
        preview_limit=125,
        hashtag_max=5,
        links_clickable=False,
        title_limit=None,
        video_aspect="9:16",
        video_resolution="1080×1920",
        video_seconds="5–90 сек",
    ),
    "youtube_shorts": PlatformProfile(
        display_name="YouTube Shorts",
        caption_limit=5000,
        preview_limit=None,
        hashtag_max=3,
        links_clickable=True,
        title_limit=100,
        video_aspect="9:16",
        video_resolution="1080×1920",
        video_seconds="до 60 сек",
    ),
    "facebook": PlatformProfile(
        display_name="Facebook Reels",
        caption_limit=2200,
        preview_limit=250,
        hashtag_max=3,
        links_clickable=True,
        title_limit=None,
        video_aspect="9:16",
        video_resolution="1080×1920 (мин. 720p)",
        video_seconds="3–90 сек",
    ),
}

# Порядок выдачи пакетов пользователю: от площадки с самыми жёсткими
# ограничениями к самой свободной, чтобы первый же пакет задавал ожидания.
_PLATFORM_ORDER = ("instagram", "youtube_shorts", "facebook")

_SHORTS_TAG = "#Shorts"

_LINK_PATTERN = re.compile(r"https?://\S+")

# Знаки, которыми ссылка может закончиться в живом тексте, не будучи их частью
# («Разбор тут: https://example.com — заходите» / «...com.»).
_LINK_TRAILING_PUNCTUATION = ".,;:!?)»\"'—–-"

_SENTENCE_END_PATTERN = re.compile(r"[.!?…]")


@dataclass(frozen=True)
class PlatformPackage:
    platform: str
    display_name: str
    title: str | None
    caption: str
    hashtags: tuple[str, ...]
    links: tuple[str, ...]
    notes: tuple[Note, ...]
    media_spec: Note


def _split_hashtag_line(text: str) -> tuple[str, tuple[str, ...]]:
    """Отделяет финальную строку хештегов от тела поста.

    Генератор просит модель поставить хештеги отдельной последней строкой
    (`_HASHTAG_INSTRUCTION` в content_generator). Строка считается хештеговой,
    только если ВСЕ её токены начинаются с решётки — иначе призыв вида
    «пишите в #комментариях» оторвал бы у поста концовку.
    """
    lines = text.rstrip().split("\n")
    if not lines:
        return text.strip(), ()

    tokens = lines[-1].split()
    if tokens and all(token.startswith("#") for token in tokens):
        body = "\n".join(lines[:-1]).rstrip()
        return body, tuple(tokens)

    return text.strip(), ()


def _extract_links(text: str) -> tuple[str, ...]:
    links = []
    for match in _LINK_PATTERN.findall(text):
        cleaned = match.rstrip(_LINK_TRAILING_PUNCTUATION)
        if cleaned and cleaned not in links:
            links.append(cleaned)
    return tuple(links)


def _fit_hashtags(
    hashtags: tuple[str, ...], profile: PlatformProfile, platform: str
) -> tuple[tuple[str, ...], bool]:
    tags = list(hashtags)

    # #Shorts ставится первым и до обрезки: без него ролик рискует не попасть
    # в ленту Shorts, поэтому он важнее любого тематического тега.
    if platform == "youtube_shorts" and _SHORTS_TAG not in tags:
        tags.insert(0, _SHORTS_TAG)

    trimmed = len(tags) > profile.hashtag_max
    return tuple(tags[: profile.hashtag_max]), trimmed


def _truncate_on_word_boundary(text: str, limit: int) -> str:
    if limit <= 1:
        return "…"

    cut = text[: limit - 1]
    boundary = cut.rfind(" ")
    if boundary > 0:
        cut = cut[:boundary]
    return cut.rstrip() + "…"


def _fit_caption(
    body: str, hashtags: tuple[str, ...], profile: PlatformProfile
) -> tuple[str, bool]:
    """Укладывает тело поста в лимит, зарезервировав место под хештеги.

    Instagram считает хештеги внутри тех же 2200 символов подписи, поэтому
    урезать надо именно тело — иначе теги молча отвалились бы при обрезке.
    """
    reserved = 0
    if hashtags:
        reserved = len(" ".join(hashtags)) + 2  # два перевода строки

    available = profile.caption_limit - reserved
    if len(body) <= available:
        return body, False

    return _truncate_on_word_boundary(body, available), True


def _derive_title(body: str, limit: int) -> str:
    """Заголовок Shorts — первое предложение поста.

    Заголовок несёт на Shorts всю нагрузку (описание почти не читают), а
    первое предложение уже написано моделью как крючок — брать его дешевле
    и предсказуемее, чем просить ИИ сочинить отдельный заголовок.
    """
    first_line = body.strip().split("\n")[0].strip()
    match = _SENTENCE_END_PATTERN.search(first_line)
    title = first_line[: match.start()] if match else first_line

    title = title.strip()
    if len(title) > limit:
        title = _truncate_on_word_boundary(title, limit)
    return title


def build_package(post_text: str, platform: str) -> PlatformPackage:
    profile = PROFILES[platform]

    body, raw_hashtags = _split_hashtag_line(post_text)
    hashtags, hashtags_trimmed = _fit_hashtags(raw_hashtags, profile, platform)
    caption, caption_truncated = _fit_caption(body, hashtags, profile)
    links = _extract_links(post_text)

    notes: list[Note] = []
    if links and not profile.links_clickable:
        notes.append(Note("package_note_links_not_clickable", {"count": len(links)}))
    if caption_truncated:
        notes.append(Note("package_note_caption_truncated", {"limit": profile.caption_limit}))
    if hashtags_trimmed:
        notes.append(Note("package_note_hashtags_trimmed", {"max": profile.hashtag_max}))
    if profile.preview_limit is not None:
        notes.append(Note("package_note_preview", {"preview": profile.preview_limit}))
    # Раскрытие ИИ-контента на YouTube обязательно и наказуемо при
    # несоблюдении, у Meta — маркировка «AI info»; напоминание показывается
    # всегда, а не только когда в посте есть видео, потому что бот не знает,
    # что именно пользователь приложит к тексту руками.
    notes.append(Note("package_note_ai_disclosure", {}))

    title = _derive_title(body, profile.title_limit) if profile.title_limit else None

    return PlatformPackage(
        platform=platform,
        display_name=profile.display_name,
        title=title,
        caption=caption,
        hashtags=hashtags,
        links=links,
        notes=tuple(notes),
        media_spec=Note(
            MEDIA_SPEC_KEY,
            {
                "aspect": profile.video_aspect,
                "resolution": profile.video_resolution,
                "seconds": profile.video_seconds,
            },
        ),
    )


def build_all_packages(post_text: str) -> tuple[PlatformPackage, ...]:
    return tuple(build_package(post_text, platform) for platform in _PLATFORM_ORDER)
