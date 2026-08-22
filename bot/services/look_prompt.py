"""Сборка промпта образа по рецепту, купленному неудачными попытками.

Правила взяты из `docs/reference-video-avatar-engines.md` и живут здесь, а не
в тексте приглашения: пользователь описывает одежду и место своими словами,
а композицию и позу держит код. Общий план в кадре 512×512 оставляет рту
двадцать пикселей и делает бессмысленным любой рендер — это уже стоило
одного несправедливо забракованного движка.
"""

from __future__ import annotations

# Тянут модель к обобщённому модельному лицу вместо лица пользователя.
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
    "каре",
    "стрижк",
    "чёлк",
    "челк",
    "hair",
    "haircut",
    "bangs",
    "ponytail",
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
    return any(word in lowered for word in _HAIR_WORDS)


def build_look_prompt(description: str) -> str:
    cleaned = description.strip()
    lowered = cleaned.lower()
    for phrase in BANNED_PHRASES:
        while phrase in lowered:
            start = lowered.index(phrase)
            cleaned = cleaned[:start] + cleaned[start + len(phrase) :]
            lowered = cleaned.lower()

    # Пустое описание — это «оставь как есть, только приведи кадр к портрету»,
    # и правил для такого запроса достаточно.
    cleaned = " ".join(cleaned.replace(" ,", ",").split()).strip(" ,")
    return f"{_RULES} {cleaned}".strip() if cleaned else _RULES
