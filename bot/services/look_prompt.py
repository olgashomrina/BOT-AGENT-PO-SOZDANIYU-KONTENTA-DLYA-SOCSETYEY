"""Сборка промпта образа по рецепту, купленному неудачными попытками.

Правила взяты из `docs/reference-video-avatar-engines.md` и живут здесь, а не
в тексте приглашения: пользователь описывает одежду и место своими словами,
а композицию и позу держит код. Общий план в кадре 512×512 оставляет рту
двадцать пикселей и делает бессмысленным любой рендер — это уже стоило
одного несправедливо забракованного движка.
"""

from __future__ import annotations

import re

# Тянут модель к обобщённому модельному лицу вместо лица пользователя.
# Порядок важен: более длинные фразы должны идти раньше своих же подстрок
# ("editorial fashion photography" содержит и "editorial fashion", и
# "fashion photography"), иначе после удаления длинной фразы короткая
# уже не найдётся, а от неё сначала оторвётся кусок текста.
BANNED_PHRASES = (
    "editorial fashion photography",
    "editorial fashion",
    "fashion photography",
    "supermodel",
    "beauty retouch",
)

_HAIR_WORDS = (
    "причес",
    "причёс",
    "волос",
    # «каре» совпадает и с причёской, и с вырезом «каре» на одежде: цена
    # ложного срабатывания — одна лишняя фраза в предупреждении, а цена
    # пропуска реальной просьбы подстричься — необъявленное изменение
    # причёски. Поэтому оставляем как есть.
    "каре",
    "стрижк",
    "чёлк",
    "челк",
    "hair",
    "haircut",
    "bangs",
    "ponytail",
)

# Русские основы ищем по префиксу слова (без \b на конце — чтобы
# "волос" находил "волосы"); английские слова — целиком, с \b с обеих сторон,
# иначе "hair" находился бы внутри "chair"/"armchair"/"wheelchair".
_HAIR_PATTERNS = tuple(
    re.compile(rf"\b{re.escape(word)}" if not word.isascii() else rf"\b{re.escape(word)}\b")
    for word in _HAIR_WORDS
)

# Композиция, поза и опора на одно лицо — то, что модель обязана сохранить.
_RULES = (
    "Close-up portrait, head and shoulders filling the frame. "
    "Frontal pose, calm expression, the same face as in the reference photo, "
    "eyes to the camera. No furniture, no props, no other people. "
    "Plain natural photograph, not a magazine shoot."
)


def mentions_hair(description: str) -> bool:
    """Просит ли описание тронуть причёску.

    Владелец сознательно разрешила такие описания, но модель на них охотно
    «улучшает» длину и волну и уводит лицо, поэтому экран показывает
    предупреждение — а для этого сначала надо распознать сам случай.
    """
    lowered = description.lower()
    return any(pattern.search(lowered) for pattern in _HAIR_PATTERNS)


def build_look_prompt(description: str) -> str:
    cleaned = description.strip()
    for phrase in BANNED_PHRASES:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        cleaned = pattern.sub("", cleaned)

    # Пустое описание — это «оставь как есть, только приведи кадр к портрету»,
    # и правил для такого запроса достаточно.
    # Сначала схлопываем цепочки запятых, оставшиеся после вырезания фразы
    # (", ," → ", "), затем схлопываем пробелы и обрезаем края от пробелов
    # и запятых — иначе после вырезания фразы в середине останется ",,".
    cleaned = re.sub(r"(?:\s*,\s*)+", ", ", cleaned)
    cleaned = " ".join(cleaned.split()).strip(" ,")
    return f"{_RULES} {cleaned}".strip() if cleaned else _RULES
