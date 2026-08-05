"""Бюджет длины поста под лимиты Telegram.

WHY отдельный модуль, а не пара функций в content_generator: здесь нет и не
должно появиться ни одного сетевого вызова и ни одного обращения к ИИ — всё
это детерминированные преобразования текста, которые тестируются без единого
мока (тот же принцип, что в bot/services/platform_package.py).

WHY длина считается не через len(): Telegram меряет сообщения в кодовых
единицах UTF-16, а не в символах Python. Обычное эмодзи занимает две единицы,
составное — больше. Промпт бота просит модель ставить 3-4 эмодзи, так что
расхождение возникает в каждом посте, и len() систематически занижает длину.

Названия пресетов, видимые пользователю, здесь намеренно НЕ хранятся: модуль
отдаёт ключи, а подписи берутся из локалей — иначе он стал бы зависеть от
языка интерфейса.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Жёсткий потолок: лимит подписи к фото/видео в Bot API. У обычного текстового
# сообщения лимит 4096, но пост может уйти с картинкой (в том числе
# прикреплённой уже после генерации текста), поэтому за общий потолок берётся
# меньший из двух — тогда «влезает всегда» выполняется по построению.
TELEGRAM_CAPTION_LIMIT = 1024


@dataclass(frozen=True)
class LengthPreset:
    key: str
    # Число, которое уходит в промпт. Формулируется в обычных символах:
    # считать UTF-16 модель всё равно не умеет.
    target_chars: int
    # Потолок, при превышении которого включается страховка. Меряется в
    # UTF-16. Разрыв между target_chars и max_units как раз и покрывает
    # разницу между «символами» модели и единицами Telegram.
    max_units: int

    @property
    def retry_target_chars(self) -> int:
        # Перезапрашивать с тем же числом бессмысленно: модель уже один раз
        # его не удержала. Просим заметно меньше, чтобы вторая попытка имела
        # запас.
        return int(self.target_chars * 0.8)


PRESETS: dict[str, LengthPreset] = {
    "short": LengthPreset("short", 400, 500),
    "medium": LengthPreset("medium", 700, 800),
    "expanded": LengthPreset("expanded", 950, TELEGRAM_CAPTION_LIMIT),
}

DEFAULT_PRESET = "medium"

# Порядок от короткого к длинному: по нему ходит кнопка «Короче».
_LADDER = ("short", "medium", "expanded")

_HASHTAG_SEPARATOR = "\n\n"

# Конец предложения плюс возможные закрывающие кавычки/скобки, после которых
# идёт пробел или конец строки. Просмотр вперёд, а не поглощение, чтобы
# match.end() указывал сразу за знаком препинания.
_SENTENCE_END_PATTERN = re.compile(r"[.!?…][\"'»)]*(?=\s|$)")


def get_preset(key: str | None) -> LengthPreset:
    """Пресет по ключу; неизвестный ключ молча становится значением по умолчанию.

    Неизвестный ключ реален: базу могли поправить руками или откатить версию
    бота. Уронить из-за этого генерацию поста было бы несоразмерно.
    """
    return PRESETS.get(key or "", PRESETS[DEFAULT_PRESET])


def next_shorter(key: str | None) -> str | None:
    """Следующий пресет вниз по лестнице; None, если уже самый короткий."""
    index = _LADDER.index(get_preset(key).key)
    return _LADDER[index - 1] if index > 0 else None


def measure(text: str) -> int:
    """Длина в кодовых единицах UTF-16 — так, как её считает Telegram."""
    return len(text.encode("utf-16-le")) // 2


def fits(text: str, max_units: int) -> bool:
    return measure(text) <= max_units


def trim(text: str, max_units: int) -> str:
    """Укладывает текст в лимит, обрезая по границе предложения.

    Крайняя мера: сначала объём задаётся промптом, потом делается перезапрос,
    и только если не помогло — вызывается это. Режем по предложениям, а не по
    символам, чтобы пост не обрывался на полуслове.
    """
    if fits(text, max_units):
        return text

    body, hashtags = _split_hashtag_line(text)
    if hashtags:
        tail = _HASHTAG_SEPARATOR + " ".join(hashtags)
        available = max_units - measure(tail)
        # Хештеги обычно короткие, но если под них ушёл весь лимит, спасать
        # уже нечего — режем текст целиком вместе с ними.
        if available > 1:
            return _trim_body(body, available) + tail

    return _trim_body(text, max_units)


def _split_hashtag_line(text: str) -> tuple[str, tuple[str, ...]]:
    """Отделяет финальную строку хештегов от тела поста.

    Строка считается хештеговой, только если ВСЕ её токены начинаются с
    решётки — иначе призыв вида «пишите в #комментариях» оторвал бы у поста
    концовку.

    WHY это не переиспользуется из platform_package: там такая же по смыслу
    функция приватная, обслуживает правила чужих площадок и меряет через
    len(). Связывать два модуля ради десяти строк дороже, чем повторить их.
    """
    lines = text.rstrip().split("\n")
    if not lines:
        return text.strip(), ()

    tokens = lines[-1].split()
    if tokens and all(token.startswith("#") for token in tokens):
        return "\n".join(lines[:-1]).rstrip(), tuple(tokens)

    return text.strip(), ()


def _trim_body(body: str, max_units: int) -> str:
    cut = _cut_to_units(body, max_units)
    matches = list(_SENTENCE_END_PATTERN.finditer(cut))
    if matches:
        return cut[: matches[-1].end()].rstrip()
    return _trim_to_word(body, max_units)


def _trim_to_word(text: str, max_units: int) -> str:
    if max_units <= 1:
        return "…"

    # Минус единица — под многоточие, которое добавляется в конце.
    cut = _cut_to_units(text, max_units - 1)
    boundary = cut.rfind(" ")
    if boundary > 0:
        cut = cut[:boundary]
    return cut.rstrip() + "…"


def _cut_to_units(text: str, units: int) -> str:
    """Обрезка ровно по кодовым единицам UTF-16.

    errors="ignore" отбрасывает половину суррогатной пары, если разрез пришёлся
    на середину эмодзи: лучше потерять один символ, чем вернуть «�».
    """
    if measure(text) <= units:
        return text
    return text.encode("utf-16-le")[: units * 2].decode("utf-16-le", errors="ignore")


# Инструкции написаны по-английски, как и остальные промпты в проекте: язык
# самого поста задаётся отдельной строкой промпта, а служебные указания
# остаются однозначными независимо от него.
_BUDGET_INSTRUCTION = (
    "Hard length limit: the entire post must be at most {target} characters, "
    "counting spaces, emoji, every URL in full and any hashtags. Aim for "
    "roughly that length and never exceed it. The closing call-to-action must "
    "fit inside the limit — do not drop it and do not end mid-thought."
)

_RETRY_INSTRUCTION = (
    "Length is the top priority for this version: the entire post must be at "
    "most {target} characters, counting spaces, emoji, every URL in full and "
    "any hashtags. Keep the core message and keep the closing call-to-action "
    "inside that limit."
)


def build_budget_instruction(preset: LengthPreset) -> str:
    return _BUDGET_INSTRUCTION.format(target=preset.target_chars)


def build_retry_instruction(preset: LengthPreset) -> str:
    return _RETRY_INSTRUCTION.format(target=preset.retry_target_chars)
