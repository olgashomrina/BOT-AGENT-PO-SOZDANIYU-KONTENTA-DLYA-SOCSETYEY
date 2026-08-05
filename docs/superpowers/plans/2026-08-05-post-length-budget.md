# Post Length Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать так, чтобы Telegram-посты генерировались в объёме, который гарантированно помещается в пост канала (в том числе с картинкой), а пользователь мог выбрать один из трёх объёмов.

**Architecture:** Новый детерминированный модуль `bot/services/post_length.py` — единственный источник правды про пресеты, измерение длины в UTF-16 и обрезку. `content_generator` подставляет бюджет в промпт и следит за одним перезапросом. Выбор пользователя хранится в `users.post_length` и попадает в генерацию из трёх хендлеров.

**Tech Stack:** Python 3.14, aiogram 3.29.1, sqlite3 (стандартная библиотека), pytest 8.3.4 + pytest-asyncio 0.25.2.

**Спека:** `docs/superpowers/specs/2026-08-05-post-length-budget-design.md`

## Global Constraints

- Жёсткий потолок Telegram: **1024** кодовых единицы UTF-16 (лимит подписи к медиа). Ни один пресет его не превышает.
- Длина везде меряется в кодовых единицах UTF-16 (`len(text.encode("utf-16-le")) // 2`), а не через `len()`. Эмодзи — 2 единицы.
- Ключи пресетов: `"short"`, `"medium"`, `"expanded"`. Значение по умолчанию — `"medium"`.
- Цели в промпте / потолки пресетов: short 400/500, medium 700/800, expanded 950/1024.
- `bot/services/post_length.py` не делает **ни одного** сетевого вызова и не обращается к ИИ. Импортирует только стандартную библиотеку.
- Бюджет применяется только к Telegram-вариантам. VK не трогаем.
- Все четыре локали (`ru`, `en`, `vi`, `zh`) обязаны иметь одинаковый набор ключей — это проверяет `tests/test_localization.py::test_all_locales_have_identical_keys`.
- Прод уже развёрнут, поэтому новая колонка требует явной миграции — `CREATE TABLE IF NOT EXISTS` существующую базу не обновит.
- Тесты запускаются из корня проекта: `python -m pytest`. `asyncio_mode = auto` уже настроен в `pytest.ini`.
- **В этом рабочем каталоге параллельно работают несколько сессий.** Никогда не делать `git add -A` и не коммитить «всё подряд» — только перечисленные в шаге файлы поимённо.
- Сообщения коммитов заканчиваются строкой `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## File Structure

| Файл | Ответственность |
| --- | --- |
| `bot/services/post_length.py` (новый) | Пресеты, измерение UTF-16, проверка, обрезка, фрагменты промпта. Чистая логика. |
| `tests/test_services_post_length.py` (новый) | Тесты модуля выше, без моков. |
| `bot/storage/db.py` | Колонка `users.post_length` + миграция. |
| `bot/storage/users.py` | `get_post_length` / `set_post_length`. |
| `bot/services/content_generator.py` | Бюджет в промпте, цикл «проверил → перезапросил → обрезал». |
| `bot/locales/{ru,en,vi,zh}.py` | Подписи кнопок и названия пресетов. |
| `bot/keyboards/start.py` | Кнопка объёма на экране «Создать пост» + клавиатура выбора. |
| `bot/handlers/start.py` | Открытие экрана выбора и сохранение выбора. |
| `bot/handlers/content.py`, `bot/handlers/authorpost.py`, `bot/handlers/refine.py` | Передача пресета в генерацию; лестница для «Короче»; починка обрезки подписи. |

---

### Task 1: Модуль post_length

**Files:**
- Create: `bot/services/post_length.py`
- Test: `tests/test_services_post_length.py`

**Interfaces:**
- Consumes: ничего (только стандартная библиотека).
- Produces:
  - `TELEGRAM_CAPTION_LIMIT: int = 1024`
  - `DEFAULT_PRESET: str = "medium"`
  - `PRESETS: dict[str, LengthPreset]`
  - `LengthPreset` — frozen dataclass с полями `key: str`, `target_chars: int`, `max_units: int` и свойством `retry_target_chars: int`
  - `get_preset(key: str | None) -> LengthPreset`
  - `next_shorter(key: str | None) -> str | None`
  - `measure(text: str) -> int`
  - `fits(text: str, max_units: int) -> bool`
  - `trim(text: str, max_units: int) -> str`
  - `build_budget_instruction(preset: LengthPreset) -> str`
  - `build_retry_instruction(preset: LengthPreset) -> str`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_services_post_length.py`:

```python
from __future__ import annotations

from bot.services import post_length


def test_measure_counts_ascii_like_len():
    assert post_length.measure("hello") == 5


def test_measure_counts_cyrillic_as_one_unit_each():
    assert post_length.measure("привет") == 6


def test_measure_counts_emoji_as_two_units():
    assert post_length.measure("🙂") == 2
    assert post_length.measure("привет 🙂") == 9


def test_fits_uses_utf16_units_not_python_len():
    text = "🙂" * 300

    assert len(text) == 300
    assert not post_length.fits(text, 500)
    assert post_length.fits(text, 600)


def test_no_preset_exceeds_the_telegram_caption_limit():
    for preset in post_length.PRESETS.values():
        assert preset.max_units <= post_length.TELEGRAM_CAPTION_LIMIT


def test_every_preset_targets_less_than_its_own_ceiling():
    for preset in post_length.PRESETS.values():
        assert preset.target_chars < preset.max_units


def test_default_preset_is_a_known_preset():
    assert post_length.DEFAULT_PRESET in post_length.PRESETS


def test_get_preset_falls_back_to_default_for_unknown_or_missing_key():
    assert post_length.get_preset("bogus").key == post_length.DEFAULT_PRESET
    assert post_length.get_preset(None).key == post_length.DEFAULT_PRESET


def test_next_shorter_walks_down_the_ladder():
    assert post_length.next_shorter("expanded") == "medium"
    assert post_length.next_shorter("medium") == "short"
    assert post_length.next_shorter("short") is None


def test_next_shorter_treats_an_unknown_key_as_the_default():
    assert post_length.next_shorter("bogus") == post_length.next_shorter(
        post_length.DEFAULT_PRESET
    )


def test_trim_returns_text_unchanged_when_it_fits():
    text = "Короткий пост. Заходите!"

    assert post_length.trim(text, 100) == text


def test_trim_cuts_on_a_sentence_boundary():
    text = "Первое предложение. Второе предложение. Третье предложение."

    result = post_length.trim(text, 40)

    assert result == "Первое предложение. Второе предложение."
    assert post_length.measure(result) <= 40


def test_trim_keeps_the_hashtag_line():
    body = "Первое предложение. Второе предложение. Третье предложение."
    text = f"{body}\n\n#кофе #утро"

    result = post_length.trim(text, 60)

    assert result.endswith("#кофе #утро")
    assert post_length.measure(result) <= 60


def test_trim_does_not_mistake_a_hashtag_inside_a_sentence_for_the_tag_line():
    text = "Первое предложение. Пишите в #комментариях что думаете об этом."

    result = post_length.trim(text, 25)

    assert result == "Первое предложение."


def test_trim_falls_back_to_a_word_boundary_without_sentence_ends():
    text = "слово " * 20

    result = post_length.trim(text, 50)

    assert result.endswith("…")
    assert post_length.measure(result) <= 50


def test_trim_never_returns_an_empty_string():
    text = "оченьдлинноесловобезпробеловипунктуации" * 3

    result = post_length.trim(text, 20)

    assert result
    assert post_length.measure(result) <= 20


def test_trim_does_not_split_an_emoji_in_half():
    text = "🙂" * 30

    result = post_length.trim(text, 22)

    assert "�" not in result
    assert post_length.measure(result) <= 22


def test_budget_instruction_names_the_target_number():
    preset = post_length.get_preset("short")

    assert str(preset.target_chars) in post_length.build_budget_instruction(preset)


def test_budget_instruction_mentions_urls_and_the_call_to_action():
    instruction = post_length.build_budget_instruction(post_length.get_preset("medium"))

    assert "URL" in instruction
    assert "call-to-action" in instruction


def test_retry_instruction_asks_for_less_than_the_first_attempt():
    preset = post_length.get_preset("medium")

    assert preset.retry_target_chars < preset.target_chars
    assert str(preset.retry_target_chars) in post_length.build_retry_instruction(preset)
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `python -m pytest tests/test_services_post_length.py -q`
Expected: FAIL — коллекция падает с `ModuleNotFoundError: No module named 'bot.services.post_length'`.

- [ ] **Step 3: Написать модуль**

Создать `bot/services/post_length.py`:

```python
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
```

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `python -m pytest tests/test_services_post_length.py -q`
Expected: PASS, 20 passed.

- [ ] **Step 5: Коммит**

```bash
git add bot/services/post_length.py tests/test_services_post_length.py
git commit -m "feat: add the post-length budget module

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Хранение выбранного пресета

**Files:**
- Modify: `bot/storage/db.py`
- Modify: `bot/storage/users.py`
- Test: `tests/test_storage_users.py`, `tests/test_storage_db.py`

**Interfaces:**
- Consumes: `post_length.DEFAULT_PRESET`, `post_length.get_preset` из Task 1.
- Produces:
  - `bot.storage.users.set_post_length(db_path: str, telegram_id: int, preset: str) -> None`
  - `bot.storage.users.get_post_length(db_path: str, telegram_id: int) -> str` — всегда валидный ключ пресета, для неизвестного пользователя возвращает `post_length.DEFAULT_PRESET`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/test_storage_users.py`:

```python
from bot.services import post_length
from bot.storage.users import get_post_length, set_post_length


def test_unknown_user_gets_the_default_post_length(db_path):
    assert get_post_length(db_path, 111) == post_length.DEFAULT_PRESET


def test_set_post_length_is_readable(db_path):
    set_post_length(db_path, 111, "short")

    assert get_post_length(db_path, 111) == "short"


def test_post_length_survives_other_user_settings(db_path):
    set_post_length(db_path, 111, "expanded")
    set_interface_language(db_path, 111, "en")

    assert get_post_length(db_path, 111) == "expanded"


def test_unknown_stored_preset_falls_back_to_the_default(db_path):
    # Значение могло попасть в базу от более новой версии бота или руками.
    set_post_length(db_path, 111, "bogus")

    assert get_post_length(db_path, 111) == post_length.DEFAULT_PRESET
```

Добавить в конец `tests/test_storage_db.py`:

```python
import sqlite3

from bot.storage.db import init_db
from bot.storage.users import get_post_length, set_post_length


def test_init_db_adds_post_length_to_a_pre_existing_users_table(tmp_path):
    path = str(tmp_path / "legacy.db")
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, interface_language TEXT)"
    )
    connection.commit()
    connection.close()

    init_db(path)

    set_post_length(path, 111, "short")
    assert get_post_length(path, 111) == "short"
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `python -m pytest tests/test_storage_users.py tests/test_storage_db.py -q`
Expected: FAIL — `ImportError: cannot import name 'get_post_length' from 'bot.storage.users'`.

- [ ] **Step 3: Добавить колонку и миграцию**

В `bot/storage/db.py` заменить объявление таблицы `users`:

```python
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    interface_language TEXT,
    content_language TEXT,
    channel_id INTEGER,
    pending_media_file_id TEXT,
    pending_media_type TEXT,
    onboarding_shown INTEGER,
    digest_topic TEXT,
    post_length TEXT
);
```

Добавить функцию миграции сразу после `_ensure_digest_topic_column`:

```python
def _ensure_post_length_column(connection: sqlite3.Connection) -> None:
    # Настройка объёма поста (docs/superpowers/specs/
    # 2026-08-05-post-length-budget-design.md) появилась, когда бот уже был
    # развёрнут. CREATE TABLE IF NOT EXISTS покрывает только чистые установки —
    # уже существующей базе нужна явная миграция, иначе бот упадёт на первом
    # же запросе после выката.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "post_length" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN post_length TEXT")
```

Зарегистрировать её в `init_db`, после `_ensure_digest_topic_column(connection)`:

```python
        _ensure_post_length_column(connection)
```

- [ ] **Step 4: Добавить аксессоры**

В конец `bot/storage/users.py` добавить (импорт `post_length` — в начало файла, рядом с импортом `get_connection`):

```python
from bot.services import post_length
```

```python
def set_post_length(db_path: str, telegram_id: int, preset: str) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET post_length = ? WHERE telegram_id = ?",
            (preset, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_post_length(db_path: str, telegram_id: int) -> str:
    """Всегда возвращает валидный ключ пресета, а не NULL и не мусор.

    Нормализация живёт здесь, чтобы три вызывающих хендлера не повторяли
    одну и ту же проверку. bot.services.post_length — модуль без зависимостей
    (только стандартная библиотека), поэтому импорт из storage цикла не создаёт.
    """
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT post_length FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        stored = row[0] if row else None
        return post_length.get_preset(stored).key
    finally:
        connection.close()
```

- [ ] **Step 5: Запустить тесты и убедиться, что они проходят**

Run: `python -m pytest tests/test_storage_users.py tests/test_storage_db.py -q`
Expected: PASS.

- [ ] **Step 6: Прогнать весь набор — миграция не должна ломать существующие тесты**

Run: `python -m pytest -q`
Expected: PASS (все тесты, что были зелёными до задачи, остаются зелёными).

- [ ] **Step 7: Коммит**

```bash
git add bot/storage/db.py bot/storage/users.py tests/test_storage_users.py tests/test_storage_db.py
git commit -m "feat: store the per-user post length preset

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Бюджет в генераторе (промпт + перезапрос + обрезка)

**Files:**
- Modify: `bot/services/content_generator.py`
- Test: `tests/test_content_generator.py`

**Interfaces:**
- Consumes: `post_length.get_preset`, `post_length.fits`, `post_length.trim`, `post_length.build_budget_instruction`, `post_length.build_retry_instruction` из Task 1.
- Produces:
  - `build_prompt(source_text, platform, content_language, extra_instruction=None, style_examples=None, with_hashtags=False, style_profile=None, length_preset: str | None = None) -> str`
  - `generate_variants(source_text, platform, content_language, count=3, extra_instruction=None, style_examples=None, with_hashtags=False, style_profile=None, length_preset: str | None = None) -> list[str]`
  - Правило: бюджет включается тогда и только тогда, когда `length_preset is not None`. Вызывающий код просто не передаёт его для VK.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/test_content_generator.py`:

```python
from bot.services import post_length


def test_build_prompt_includes_the_budget_when_a_preset_is_given():
    prompt = content_generator.build_prompt("текст", "telegram", "ru", length_preset="short")

    assert str(post_length.get_preset("short").target_chars) in prompt


def test_build_prompt_without_a_preset_is_unchanged_from_default():
    prompt = content_generator.build_prompt("текст", "telegram", "ru")

    assert prompt == content_generator.build_prompt(
        "текст", "telegram", "ru", length_preset=None
    )


def test_build_prompt_budget_differs_between_presets():
    short_prompt = content_generator.build_prompt(
        "текст", "telegram", "ru", length_preset="short"
    )
    expanded_prompt = content_generator.build_prompt(
        "текст", "telegram", "ru", length_preset="expanded"
    )

    assert short_prompt != expanded_prompt


@pytest.mark.asyncio
async def test_generate_variants_does_not_retry_when_the_variant_fits(monkeypatch):
    mock = AsyncMock(return_value="Короткий пост. Заходите!")
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    await content_generator.generate_variants(
        "текст", "telegram", "ru", count=2, length_preset="short"
    )

    assert mock.await_count == 2


@pytest.mark.asyncio
async def test_generate_variants_retries_once_when_the_variant_is_too_long(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=[too_long, "Коротко. Жми!"])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants(
        "текст", "telegram", "ru", count=1, length_preset="short"
    )

    assert mock.await_count == 2
    assert variants == ["Коротко. Жми!"]


@pytest.mark.asyncio
async def test_generate_variants_retry_prompt_asks_for_a_smaller_number(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=[too_long, "Коротко. Жми!"])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    await content_generator.generate_variants(
        "текст", "telegram", "ru", count=1, length_preset="short"
    )

    retry_prompt = mock.await_args_list[1].args[0]
    assert str(post_length.get_preset("short").retry_target_chars) in retry_prompt


@pytest.mark.asyncio
async def test_generate_variants_trims_when_the_retry_is_also_too_long(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=[too_long, too_long])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants(
        "текст", "telegram", "ru", count=1, length_preset="short"
    )

    assert mock.await_count == 2
    assert post_length.measure(variants[0]) <= post_length.get_preset("short").max_units


@pytest.mark.asyncio
async def test_generate_variants_returns_a_trimmed_first_attempt_when_the_retry_fails(
    monkeypatch,
):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=[too_long, AIGatewayTimeoutError("timed out")])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants(
        "текст", "telegram", "ru", count=1, length_preset="short"
    )

    assert post_length.measure(variants[0]) <= post_length.get_preset("short").max_units


@pytest.mark.asyncio
async def test_generate_variants_retries_only_the_variant_that_overshot(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=["Коротко. Жми!", too_long, "Тоже коротко. Жми!"])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants(
        "текст", "telegram", "ru", count=2, length_preset="short"
    )

    assert mock.await_count == 3
    assert variants == ["Коротко. Жми!", "Тоже коротко. Жми!"]


@pytest.mark.asyncio
async def test_generate_variants_without_a_preset_never_retries(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(return_value=too_long)
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants("текст", "vk", "ru", count=2)

    assert mock.await_count == 2
    assert variants == [too_long, too_long]
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `python -m pytest tests/test_content_generator.py -q`
Expected: FAIL — `TypeError: build_prompt() got an unexpected keyword argument 'length_preset'`.

- [ ] **Step 3: Реализовать бюджет**

В `bot/services/content_generator.py` добавить к импортам:

```python
from bot.services import ai_gateway, post_length
from bot.services.ai_gateway import AIGatewayError
```

(строку `from bot.services import ai_gateway` заменить на первую из двух.)

Заменить `build_prompt` целиком:

```python
def build_prompt(
    source_text: str,
    platform: Platform,
    content_language: str,
    extra_instruction: str | None = None,
    style_examples: list[str] | None = None,
    with_hashtags: bool = False,
    style_profile: str | None = None,
    length_preset: str | None = None,
) -> str:
    extra_line = f"{extra_instruction}\n" if extra_instruction else ""
    hashtag_line = f"{_HASHTAG_INSTRUCTION}\n" if with_hashtags else ""
    style_section = _build_style_section(style_examples, style_profile)
    budget_line = ""
    if length_preset is not None:
        budget_line = (
            post_length.build_budget_instruction(post_length.get_preset(length_preset)) + "\n"
        )
    return (
        "You are a social media copywriter. Write ONE ready-to-publish social "
        "media post based on the source material below.\n"
        f"{_PLATFORM_INSTRUCTIONS[platform]}\n"
        f"{_TONE_INSTRUCTION}\n"
        f"Write the post in this language (ISO 639-1 code): {content_language}.\n"
        f"{budget_line}"
        f"{extra_line}"
        f"{hashtag_line}"
        f"{style_section}"
        "Return only the post text itself, without any preamble, quotes or "
        "explanation.\n\n"
        f"Source material:\n{source_text}"
    )
```

Заменить `generate_variants` целиком и добавить перед ней помощник:

```python
async def _fit_to_budget(variant: str, retry_prompt: str, length_preset: str) -> str:
    """Укладывает вариант в бюджет: один перезапрос, потом обрезка.

    Перезапрос ровно один, а не цикл «пока не влезет»: цикл не даёт гарантии
    завершения, зато уверенно разгоняет счёт за ИИ. Обрезка гарантию даёт
    всегда, поэтому она и стоит последней.
    """
    preset = post_length.get_preset(length_preset)
    if post_length.fits(variant, preset.max_units):
        return variant

    try:
        retried = await ai_gateway.generate_text(retry_prompt, temperature=_VARIANT_TEMPERATURE)
    except AIGatewayError:
        # Первая генерация уже удалась и оплачена — отдаём её подрезанной.
        # Уронить весь запрос из-за необязательной второй попытки означало бы
        # взять с пользователя деньги и не отдать ничего.
        return post_length.trim(variant, preset.max_units)

    if post_length.fits(retried, preset.max_units):
        return retried
    return post_length.trim(retried, preset.max_units)


async def generate_variants(
    source_text: str,
    platform: Platform,
    content_language: str,
    count: int = 3,
    extra_instruction: str | None = None,
    style_examples: list[str] | None = None,
    with_hashtags: bool = False,
    style_profile: str | None = None,
    length_preset: str | None = None,
) -> list[str]:
    # Design call: call generate_text() `count` times with the same prompt
    # rather than asking the model for N variants in one response. Simpler
    # and more robust — a single-call "give me N options" instruction is
    # easy for a model to ignore or format inconsistently, whereas N
    # independent calls always yield N usable variants (relying on the
    # provider's own sampling randomness for variety).
    prompt = build_prompt(
        source_text,
        platform,
        content_language,
        extra_instruction,
        style_examples,
        with_hashtags,
        style_profile,
        length_preset,
    )

    # Промпт перезапроса собирается один раз на весь набор, а применяется
    # только к тем вариантам, которые не уложились: перегенерировать все
    # `count` штук из-за одного длинного значило бы платить втрое.
    retry_prompt = ""
    if length_preset is not None:
        retry_instruction = post_length.build_retry_instruction(
            post_length.get_preset(length_preset)
        )
        combined = (
            f"{extra_instruction}\n{retry_instruction}" if extra_instruction else retry_instruction
        )
        retry_prompt = build_prompt(
            source_text,
            platform,
            content_language,
            combined,
            style_examples,
            with_hashtags,
            style_profile,
            length_preset,
        )

    variants = []
    for _ in range(count):
        variant = await ai_gateway.generate_text(prompt, temperature=_VARIANT_TEMPERATURE)
        if length_preset is not None:
            variant = await _fit_to_budget(variant, retry_prompt, length_preset)
        variants.append(variant)
    return variants
```

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `python -m pytest tests/test_content_generator.py -q`
Expected: PASS. Существующие тесты этого файла тоже зелёные — `length_preset` по умолчанию `None`, поведение без него не изменилось.

- [ ] **Step 5: Коммит**

```bash
git add bot/services/content_generator.py tests/test_content_generator.py
git commit -m "feat: enforce the length budget in generated variants

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Локали и кнопка объёма на экране «Создать пост»

**Files:**
- Modify: `bot/locales/ru.py`, `bot/locales/en.py`, `bot/locales/vi.py`, `bot/locales/zh.py`
- Modify: `bot/keyboards/start.py`
- Modify: `bot/handlers/start.py` (только вызов `build_create_post_keyboard`)
- Test: `tests/test_keyboards_start.py`

**Interfaces:**
- Consumes: `post_length.PRESETS`, `post_length.DEFAULT_PRESET` (Task 1), `users.get_post_length` (Task 2).
- Produces:
  - `bot.keyboards.start.CALLBACK_POST_LENGTH = "menu:post_length"`
  - `bot.keyboards.start.CALLBACK_POST_LENGTH_SET_PREFIX = "menu:post_length:set"`
  - `bot.keyboards.start.build_create_post_keyboard(mini_app_url: str, lang: str, post_length_key: str) -> InlineKeyboardMarkup`
  - `bot.keyboards.start.build_post_length_keyboard(current_key: str, lang: str) -> InlineKeyboardMarkup`
  - Ключи локалей: `post_length_button`, `post_length_prompt`, `post_length_saved`, `post_length_short`, `post_length_medium`, `post_length_expanded`

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/test_keyboards_start.py`:

```python
from bot.keyboards.start import (
    CALLBACK_POST_LENGTH,
    CALLBACK_POST_LENGTH_SET_PREFIX,
    build_post_length_keyboard,
)
from bot.services import post_length


def test_create_post_keyboard_shows_the_current_post_length():
    keyboard = build_create_post_keyboard("", "ru", "short")

    button = keyboard.inline_keyboard[-1][0]
    assert button.callback_data == CALLBACK_POST_LENGTH
    assert get_string("post_length_short", "ru") in button.text


def test_create_post_keyboard_length_button_reflects_the_chosen_preset():
    short_button = build_create_post_keyboard("", "ru", "short").inline_keyboard[-1][0]
    expanded_button = build_create_post_keyboard("", "ru", "expanded").inline_keyboard[-1][0]

    assert short_button.text != expanded_button.text


def test_post_length_keyboard_has_a_row_per_preset():
    keyboard = build_post_length_keyboard("medium", "ru")

    assert len(keyboard.inline_keyboard) == len(post_length.PRESETS)
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callbacks == [
        f"{CALLBACK_POST_LENGTH_SET_PREFIX}:short",
        f"{CALLBACK_POST_LENGTH_SET_PREFIX}:medium",
        f"{CALLBACK_POST_LENGTH_SET_PREFIX}:expanded",
    ]


def test_post_length_keyboard_marks_the_current_preset():
    keyboard = build_post_length_keyboard("medium", "ru")

    texts = {row[0].callback_data: row[0].text for row in keyboard.inline_keyboard}
    assert texts[f"{CALLBACK_POST_LENGTH_SET_PREFIX}:medium"].startswith("✓")
    assert not texts[f"{CALLBACK_POST_LENGTH_SET_PREFIX}:short"].startswith("✓")


def test_post_length_keyboard_marks_a_different_preset_when_chosen():
    keyboard = build_post_length_keyboard("expanded", "en")

    texts = {row[0].callback_data: row[0].text for row in keyboard.inline_keyboard}
    assert texts[f"{CALLBACK_POST_LENGTH_SET_PREFIX}:expanded"].startswith("✓")
    assert not texts[f"{CALLBACK_POST_LENGTH_SET_PREFIX}:medium"].startswith("✓")
```

Обновить три существующих теста в этом же файле, которые звали клавиатуру с двумя аргументами:

```python
def test_create_post_keyboard_includes_site_button_when_url_set():
    keyboard = build_create_post_keyboard(
        "https://olgashomrina.github.io/my-lending-test/", "ru", "medium"
    )

    first_row = keyboard.inline_keyboard[0]
    assert first_row[0].text == get_string("open_site_button", "ru")
    assert first_row[0].web_app.url == "https://olgashomrina.github.io/my-lending-test/"


def test_create_post_keyboard_omits_site_button_when_url_missing():
    keyboard = build_create_post_keyboard("", "ru", "medium")

    assert len(keyboard.inline_keyboard) == 3
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_TEXT_HINT
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_PHOTO_GEN
    assert keyboard.inline_keyboard[2][0].callback_data == CALLBACK_POST_LENGTH


def test_create_post_keyboard_text_and_photo_buttons():
    keyboard = build_create_post_keyboard("https://example.com/", "vi", "medium")

    text_button = keyboard.inline_keyboard[-3][0]
    photo_button = keyboard.inline_keyboard[-2][0]
    assert text_button.text == get_string("menu_text_generation_button", "vi")
    assert text_button.callback_data == CALLBACK_TEXT_HINT
    assert photo_button.text == get_string("menu_photo_generation_button", "vi")
    assert photo_button.callback_data == CALLBACK_PHOTO_GEN
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `python -m pytest tests/test_keyboards_start.py -q`
Expected: FAIL — `ImportError: cannot import name 'CALLBACK_POST_LENGTH' from 'bot.keyboards.start'`.

- [ ] **Step 3: Добавить строки во все четыре локали**

В `bot/locales/ru.py` сразу после строки с ключом `"menu_photo_generation_button"`:

```python
    "post_length_button": "📏 Объём поста: {value}",
    "post_length_prompt": (
        "Какого объёма писать посты? Любой из вариантов гарантированно "
        "помещается в пост Telegram — даже когда к нему приложена картинка."
    ),
    "post_length_saved": "Готово. Объём поста: {value}.",
    "post_length_short": "Короткий",
    "post_length_medium": "Средний",
    "post_length_expanded": "Развёрнутый",
```

В `bot/locales/en.py` сразу после строки с ключом `"menu_photo_generation_button"`:

```python
    "post_length_button": "📏 Post length: {value}",
    "post_length_prompt": (
        "How long should your posts be? Every option is guaranteed to fit a "
        "Telegram post — even when there is an image attached."
    ),
    "post_length_saved": "Done. Post length: {value}.",
    "post_length_short": "Short",
    "post_length_medium": "Medium",
    "post_length_expanded": "Detailed",
```

В `bot/locales/vi.py` сразу после строки с ключом `"menu_photo_generation_button"`:

```python
    "post_length_button": "📏 Độ dài bài đăng: {value}",
    "post_length_prompt": (
        "Bài đăng nên dài bao nhiêu? Mọi lựa chọn đều chắc chắn vừa với một "
        "bài đăng Telegram — kể cả khi có ảnh đính kèm."
    ),
    "post_length_saved": "Xong. Độ dài bài đăng: {value}.",
    "post_length_short": "Ngắn",
    "post_length_medium": "Trung bình",
    "post_length_expanded": "Chi tiết",
```

В `bot/locales/zh.py` сразу после строки с ключом `"menu_photo_generation_button"`:

```python
    "post_length_button": "📏 帖子长度：{value}",
    "post_length_prompt": "帖子应该写多长？每个选项都保证能放进一条 Telegram 帖子——即使附带图片。",
    "post_length_saved": "已保存。帖子长度：{value}。",
    "post_length_short": "简短",
    "post_length_medium": "适中",
    "post_length_expanded": "详细",
```

- [ ] **Step 4: Обновить клавиатуры**

В `bot/keyboards/start.py` добавить константы рядом с остальными:

```python
CALLBACK_POST_LENGTH = "menu:post_length"
CALLBACK_POST_LENGTH_SET_PREFIX = "menu:post_length:set"
```

и импорт пресетов:

```python
from bot.services.post_length import PRESETS as _LENGTH_PRESETS
```

Заменить `build_create_post_keyboard` целиком:

```python
def build_create_post_keyboard(
    mini_app_url: str, lang: str, post_length_key: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if mini_app_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_string("open_site_button", lang),
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("menu_text_generation_button", lang),
                callback_data=CALLBACK_TEXT_HINT,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("menu_photo_generation_button", lang),
                callback_data=CALLBACK_PHOTO_GEN,
            )
        ]
    )
    # Текущее значение стоит прямо в подписи: настройка меняется редко, и без
    # него пользователю пришлось бы открывать экран только чтобы вспомнить,
    # что там выбрано.
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string(
                    "post_length_button",
                    lang,
                    value=get_string(f"post_length_{post_length_key}", lang),
                ),
                callback_data=CALLBACK_POST_LENGTH,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_post_length_keyboard(current_key: str, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for key in _LENGTH_PRESETS:
        label = get_string(f"post_length_{key}", lang)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✓ {label}" if key == current_key else label,
                    callback_data=f"{CALLBACK_POST_LENGTH_SET_PREFIX}:{key}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 5: Обновить единственного вызывающего**

В `bot/handlers/start.py` добавить импорт рядом с остальными импортами из `bot.storage.users`:

```python
    get_post_length,
```

и заменить тело `on_menu_create_post`:

```python
@router.callback_query(F.data == CALLBACK_CREATE_POST)
async def on_menu_create_post(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    settings = load_settings()
    await callback.message.answer(
        get_string("menu_cta_button", language),
        reply_markup=build_create_post_keyboard(
            settings.mini_app_url, language, get_post_length(db_path, telegram_id)
        ),
    )
    await callback.answer()
```

- [ ] **Step 6: Запустить тесты и убедиться, что они проходят**

Run: `python -m pytest tests/test_keyboards_start.py tests/test_localization.py -q`
Expected: PASS. `test_all_locales_have_identical_keys` подтверждает, что шесть ключей добавлены во все четыре локали.

- [ ] **Step 7: Коммит**

```bash
git add bot/locales/ru.py bot/locales/en.py bot/locales/vi.py bot/locales/zh.py bot/keyboards/start.py bot/handlers/start.py tests/test_keyboards_start.py
git commit -m "feat: show the post length setting on the create-post screen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Хендлеры выбора объёма

**Files:**
- Modify: `bot/handlers/start.py`
- Test: `tests/test_handlers_start.py`

**Interfaces:**
- Consumes: `build_post_length_keyboard`, `CALLBACK_POST_LENGTH`, `CALLBACK_POST_LENGTH_SET_PREFIX` (Task 4); `get_post_length`, `set_post_length` (Task 2); `post_length.PRESETS` (Task 1).
- Produces:
  - `bot.handlers.start.on_menu_post_length(callback: CallbackQuery, db_path: str) -> None`
  - `bot.handlers.start.on_set_post_length(callback: CallbackQuery, db_path: str) -> None`

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/test_handlers_start.py`:

```python
from bot.handlers.start import on_menu_post_length, on_set_post_length
from bot.keyboards.start import CALLBACK_POST_LENGTH_SET_PREFIX
from bot.storage.users import get_post_length, set_post_length
from bot.storage.whitelist import add_user


def _make_length_callback(telegram_id: int, data: str, language_code: str = "ru"):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    callback.data = data
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_post_length_screen_shows_the_current_choice(db_path):
    add_user(db_path, 111)
    set_post_length(db_path, 111, "expanded")
    callback = _make_length_callback(111, "menu:post_length")

    await on_menu_post_length(callback, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("post_length_prompt", "ru")
    keyboard = kwargs["reply_markup"]
    marked = [row[0].text for row in keyboard.inline_keyboard if row[0].text.startswith("✓")]
    assert marked == [f"✓ {get_string('post_length_expanded', 'ru')}"]


@pytest.mark.asyncio
async def test_choosing_a_preset_saves_it(db_path):
    add_user(db_path, 111)
    callback = _make_length_callback(111, f"{CALLBACK_POST_LENGTH_SET_PREFIX}:short")

    await on_set_post_length(callback, db_path)

    assert get_post_length(db_path, 111) == "short"


@pytest.mark.asyncio
async def test_choosing_a_preset_confirms_and_returns_to_the_create_post_screen(db_path):
    add_user(db_path, 111)
    callback = _make_length_callback(111, f"{CALLBACK_POST_LENGTH_SET_PREFIX}:short")

    await on_set_post_length(callback, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string(
        "post_length_saved", "ru", value=get_string("post_length_short", "ru")
    )
    callbacks = [
        button.callback_data
        for row in kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert CALLBACK_TEXT_HINT in callbacks
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_unknown_preset_key_does_not_change_the_setting(db_path):
    # Значение callback_data приходит от клиента, а клиент можно подменить.
    add_user(db_path, 111)
    set_post_length(db_path, 111, "medium")
    callback = _make_length_callback(111, f"{CALLBACK_POST_LENGTH_SET_PREFIX}:bogus")

    await on_set_post_length(callback, db_path)

    assert get_post_length(db_path, 111) == "medium"
    callback.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_length_screen_blocked_for_a_user_not_in_the_whitelist(db_path, monkeypatch):
    monkeypatch.setenv("WHITELIST_ENABLED", "true")
    callback = _make_length_callback(999, "menu:post_length")

    await on_menu_post_length(callback, db_path)

    keyboards = [
        kwargs.get("reply_markup") for _, kwargs in callback.message.answer.call_args_list
    ]
    assert all(keyboard is None for keyboard in keyboards)
```

`CALLBACK_TEXT_HINT` и `add_user` в этом файле уже импортированы (строки 187 и 189) — повторно их добавлять не нужно. В файле принят стиль с несколькими блоками импортов по ходу текста, поэтому новые импорты ставятся рядом с добавляемыми тестами.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `python -m pytest tests/test_handlers_start.py -q`
Expected: FAIL — `ImportError: cannot import name 'on_menu_post_length' from 'bot.handlers.start'`.

- [ ] **Step 3: Написать хендлеры**

В `bot/handlers/start.py` расширить импорты из `bot.keyboards.start`:

```python
    CALLBACK_POST_LENGTH,
    CALLBACK_POST_LENGTH_SET_PREFIX,
    build_post_length_keyboard,
```

добавить импорты:

```python
from bot.services.post_length import PRESETS as _LENGTH_PRESETS
```

и в блок импортов из `bot.storage.users`:

```python
    set_post_length,
```

Добавить два хендлера сразу после `on_menu_create_post`:

```python
@router.callback_query(F.data == CALLBACK_POST_LENGTH)
async def on_menu_post_length(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    await callback.message.answer(
        get_string("post_length_prompt", language),
        reply_markup=build_post_length_keyboard(
            get_post_length(db_path, telegram_id), language
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(CALLBACK_POST_LENGTH_SET_PREFIX))
async def on_set_post_length(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    # callback_data приходит от клиента, а клиент может быть модифицирован —
    # тот же приём защиты, что в bot/handlers/authorpost.py. Записать в базу
    # неизвестный ключ не смертельно (get_post_length его нормализует), но
    # молча подтвердить пользователю несуществующий выбор — хуже.
    key = callback.data.split(":")[-1]
    if key not in _LENGTH_PRESETS:
        await safe_answer(callback)
        return

    set_post_length(db_path, telegram_id, key)

    settings = load_settings()
    await callback.message.answer(
        get_string("post_length_saved", language, value=get_string(f"post_length_{key}", language)),
        reply_markup=build_create_post_keyboard(settings.mini_app_url, language, key),
    )
    await callback.answer()
```

**Важно про порядок роутинга:** `on_menu_create_post` объявлен через `F.data == CALLBACK_CREATE_POST`, а `on_menu_post_length` — через `F.data == CALLBACK_POST_LENGTH`, то есть точные сравнения. Только `on_set_post_length` использует `startswith`, и его префикс `"menu:post_length:set"` длиннее `"menu:post_length"`, поэтому пересечения нет.

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `python -m pytest tests/test_handlers_start.py -q`
Expected: PASS.

- [ ] **Step 5: Прогнать весь набор**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add bot/handlers/start.py tests/test_handlers_start.py
git commit -m "feat: let the user pick a post length preset

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Передать пресет в генерацию

**Files:**
- Modify: `bot/handlers/content.py:380-400`
- Modify: `bot/handlers/authorpost.py:355-370`
- Modify: `bot/handlers/refine.py:61-147`
- Test: `tests/test_handlers_refine.py`, `tests/test_handlers_content_flow.py`

**Interfaces:**
- Consumes: `users.get_post_length` (Task 2), `content_generator.generate_variants(..., length_preset=...)` (Task 3), `post_length.next_shorter` (Task 1).
- Produces: `bot.handlers.refine._generate_and_send(callback, state, db_path, platform, shorten: bool)` — параметр `extra_instruction` заменён на `shorten`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/test_handlers_refine.py`:

```python
from bot.storage.users import set_post_length


@pytest.mark.asyncio
async def test_refine_more_passes_the_users_preset_for_telegram(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)
    set_post_length(db_path, TELEGRAM_ID, "expanded")

    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    await on_refine_more(callback, state, db_path)

    assert mock_generate.await_args.kwargs["length_preset"] == "expanded"


@pytest.mark.asyncio
async def test_refine_more_sends_no_preset_for_vk(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path, platform="vk")

    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:vk:1")
    await on_refine_more(callback, state, db_path)

    assert mock_generate.await_args.kwargs["length_preset"] is None


@pytest.mark.asyncio
async def test_shorten_steps_one_preset_down_instead_of_wording(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)
    set_post_length(db_path, TELEGRAM_ID, "expanded")

    mock_generate = AsyncMock(return_value=["Короче"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:shorten:telegram:1")
    await on_refine_shorten(callback, state, db_path)

    assert mock_generate.await_args.kwargs["length_preset"] == "medium"
    assert mock_generate.await_args.kwargs["extra_instruction"] is None


@pytest.mark.asyncio
async def test_shorten_on_the_shortest_preset_keeps_the_wording(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)
    set_post_length(db_path, TELEGRAM_ID, "short")

    mock_generate = AsyncMock(return_value=["Ещё короче"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:shorten:telegram:1")
    await on_refine_shorten(callback, state, db_path)

    assert mock_generate.await_args.kwargs["length_preset"] == "short"
    assert (
        mock_generate.await_args.kwargs["extra_instruction"]
        == content_generator.SHORTEN_INSTRUCTION
    )


@pytest.mark.asyncio
async def test_shorten_does_not_change_the_saved_preset(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)
    set_post_length(db_path, TELEGRAM_ID, "expanded")

    monkeypatch.setattr(content_generator, "generate_variants", AsyncMock(return_value=["x"]))

    callback = _make_callback(data="refine:shorten:telegram:1")
    await on_refine_shorten(callback, state, db_path)

    assert get_post_length(db_path, TELEGRAM_ID) == "expanded"
```

Импорт `get_post_length` добавить в шапку файла к существующему импорту из `bot.storage.users`.

Обновить два существующих теста в `tests/test_handlers_refine.py`, которые сверяют полный набор kwargs:

```python
    mock_generate.assert_awaited_once_with(
        "Исходный текст статьи.",
        "telegram",
        "ru",
        count=1,
        extra_instruction=None,
        style_examples=[],
        with_hashtags=False,
        style_profile=None,
        length_preset="medium",
    )
```

(в `test_refine_more_generates_and_sends_new_variant`) и

```python
    mock_generate.assert_awaited_once_with(
        "Исходный текст статьи.",
        "vk",
        "ru",
        count=1,
        extra_instruction=content_generator.SHORTEN_INSTRUCTION,
        style_examples=[],
        with_hashtags=False,
        style_profile=None,
        length_preset=None,
    )
```

(в `test_refine_shorten_passes_shorten_instruction`).

Добавить в конец `tests/test_handlers_content_flow.py`:

```python
from bot.storage.users import set_post_length


@pytest.mark.asyncio
async def test_content_flow_budgets_telegram_but_not_vk(db_path, monkeypatch):
    message = _make_message(text="Просто текст")
    bot = _make_bot()
    state = _make_state()
    set_post_length(db_path, TELEGRAM_ID, "short")

    mock_generate_variants = _mock_generate_variants(monkeypatch)

    await route_content(message, db_path, bot, state)

    telegram_call, vk_call = mock_generate_variants.await_args_list
    assert telegram_call.kwargs["length_preset"] == "short"
    assert "length_preset" not in vk_call.kwargs
```

`TELEGRAM_ID` уже определён в этом файле (строка 34, значение `111`) и служит значением по умолчанию для `_make_message` — отдельного импорта не требуется.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `python -m pytest tests/test_handlers_refine.py tests/test_handlers_content_flow.py -q`
Expected: FAIL — `KeyError: 'length_preset'` и несовпадение ожидаемых аргументов в `assert_awaited_once_with`.

- [ ] **Step 3: Основной поток генерации**

В `bot/handlers/content.py` добавить `get_post_length` в импорт из `bot.storage.users` и заменить блок вызовов в `_finish`:

```python
    try:
        telegram_variants = await content_generator.generate_variants(
            text,
            "telegram",
            content_language,
            count=settings.content_variants_count,
            style_examples=style_examples,
            style_profile=style_profile,
            length_preset=get_post_length(db_path, telegram_id),
        )
        vk_variants = await content_generator.generate_variants(
            text,
            "vk",
            content_language,
            count=settings.content_variants_count,
            style_examples=style_examples,
            style_profile=style_profile,
        )
```

- [ ] **Step 4: Авторский пост из дайджеста**

В `bot/handlers/authorpost.py` добавить `get_post_length` в импорт из `bot.storage.users` и заменить вызов генерации:

```python
            variants = await content_generator.generate_variants(
                source_text,
                platform,
                content_language,
                count=settings.content_variants_count,
                style_examples=style_examples,
                with_hashtags=True,
                style_profile=style_profile,
                # Бюджет — свойство Telegram-поста: у VK лимит на порядок
                # больше, и урезать там нечего.
                length_preset=(
                    get_post_length(db_path, telegram_id) if platform == "telegram" else None
                ),
            )
```

Переменная `telegram_id` в этой функции уже есть — она используется строкой выше в `get_style_examples(db_path, telegram_id)`.

- [ ] **Step 5: Кнопки «Ещё» и «Короче»**

В `bot/handlers/refine.py` добавить `post_length` в импорт из `bot.services` и `get_post_length` в импорт из `bot.storage.users`. Заменить сигнатуру и начало `_generate_and_send`, а также два хендлера:

```python
async def _generate_and_send(
    callback: CallbackQuery,
    state: FSMContext,
    db_path: str,
    platform: str,
    shorten: bool,
) -> None:
```

Внутри `_generate_and_send`, сразу перед блоком `try:` с вызовом `generate_variants`, добавить:

```python
    # «Короче» теперь означает «на один пресет короче», а не расплывчатое
    # словесное указание: у нижней ступени лестницы шага нет, поэтому там
    # сохраняется прежняя формулировка. У VK пресетов нет вовсе.
    extra_instruction: str | None = None
    length_preset: str | None = None
    if platform == "telegram":
        length_preset = get_post_length(db_path, telegram_id)
        if shorten:
            shorter = post_length.next_shorter(length_preset)
            if shorter is None:
                extra_instruction = SHORTEN_INSTRUCTION
            else:
                length_preset = shorter
    elif shorten:
        extra_instruction = SHORTEN_INSTRUCTION
```

и передать оба значения в вызов:

```python
        variants = await content_generator.generate_variants(
            source_text,
            platform,
            content_language,
            count=1,
            extra_instruction=extra_instruction,
            style_examples=style_examples,
            with_hashtags=with_hashtags,
            style_profile=style_profile,
            length_preset=length_preset,
        )
```

Заменить оба хендлера:

```python
@router.callback_query(F.data.startswith("refine:more:"))
async def on_refine_more(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    platform = callback.data.split(":")[2]
    await _generate_and_send(callback, state, db_path, platform, shorten=False)


@router.callback_query(F.data.startswith("refine:shorten:"))
async def on_refine_shorten(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    platform = callback.data.split(":")[2]
    await _generate_and_send(callback, state, db_path, platform, shorten=True)
```

- [ ] **Step 6: Запустить тесты и убедиться, что они проходят**

Run: `python -m pytest tests/test_handlers_refine.py tests/test_handlers_content_flow.py tests/test_handlers_authorpost.py -q`
Expected: PASS.

- [ ] **Step 7: Прогнать весь набор**

Run: `python -m pytest -q`
Expected: PASS. Если какой-то ещё тест сверяет полный набор kwargs вызова `generate_variants` через `assert_awaited_once_with`, добавить в ожидание `length_preset=...` с тем значением, которое соответствует площадке в этом тесте (`None` для VK, ключ пресета для Telegram).

- [ ] **Step 8: Коммит**

```bash
git add bot/handlers/content.py bot/handlers/authorpost.py bot/handlers/refine.py tests/test_handlers_refine.py tests/test_handlers_content_flow.py
git commit -m "feat: generate telegram posts within the chosen length budget

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Починить обрезку подписи при публикации

**Files:**
- Modify: `bot/handlers/refine.py:48-58` (удаление), `bot/handlers/refine.py:167-194`
- Test: `tests/test_handlers_refine.py`

**Interfaces:**
- Consumes: `post_length.trim`, `post_length.TELEGRAM_CAPTION_LIMIT`, `post_length.measure` (Task 1).
- Produces: ничего нового наружу; `_truncate_caption` и `_TELEGRAM_CAPTION_LIMIT` удаляются из `refine.py`.

- [ ] **Step 1: Заменить существующий тест обрезки и добавить регрессию**

В `tests/test_handlers_refine.py` заменить `test_publish_with_pending_photo_truncates_oversized_caption` целиком:

```python
@pytest.mark.asyncio
async def test_publish_with_pending_photo_trims_the_caption_on_a_sentence_boundary(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await _seed_finished_session(state, db_path)

    oversized_text = "Очень длинное предложение про кофе. " * 40
    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = oversized_text
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    _, kwargs = bot.send_photo.call_args
    caption = kwargs["caption"]
    assert post_length.measure(caption) <= post_length.TELEGRAM_CAPTION_LIMIT
    assert caption.endswith("кофе.")


@pytest.mark.asyncio
async def test_publish_with_pending_photo_never_splits_an_html_entity(db_path):
    # Регрессия: раньше подпись резалась уже ПОСЛЕ экранирования, поэтому
    # разрез мог прийтись на середину «&amp;» — Telegram отклонял такое
    # сообщение целиком, и публикация падала.
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await _seed_finished_session(state, db_path)

    oversized_text = "Кофе & чай. " * 120
    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = oversized_text
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    _, kwargs = bot.send_photo.call_args
    caption = kwargs["caption"]
    plain = caption.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # Подпись обязана быть корректным экранированием какого-то целого текста,
    # который сам укладывается в лимит Telegram (он меряет разобранный текст).
    assert caption == output_formatter.format_variant(plain)
    assert post_length.measure(plain) <= post_length.TELEGRAM_CAPTION_LIMIT


@pytest.mark.asyncio
async def test_publish_without_media_does_not_trim(db_path):
    # Без картинки лимит 4096, а не 1024 — резать нечего.
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    state = _make_state()
    await _seed_finished_session(state, db_path)

    long_text = "Очень длинное предложение про кофе. " * 40
    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = long_text
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    _, kwargs = bot.send_message.call_args
    assert kwargs == {"parse_mode": output_formatter.PARSE_MODE}
    assert bot.send_message.call_args.args[1] == output_formatter.format_variant(long_text)
```

Импорт `post_length` добавить в шапку файла к существующему `from bot.services import ai_gateway, content_generator, output_formatter`.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `python -m pytest tests/test_handlers_refine.py -k "publish and (trims or entity or does_not_trim)" -q`
Expected: FAIL — `test_publish_with_pending_photo_never_splits_an_html_entity` падает, потому что нынешний код режет уже экранированную строку.

- [ ] **Step 3: Удалить старую обрезку**

В `bot/handlers/refine.py` удалить константу и функцию целиком:

```python
_TELEGRAM_CAPTION_LIMIT = 1024


def _truncate_caption(text: str) -> str:
    if len(text) <= _TELEGRAM_CAPTION_LIMIT:
        return text
    return text[: _TELEGRAM_CAPTION_LIMIT - 1] + "…"
```

(вместе с комментарием над `_TELEGRAM_CAPTION_LIMIT`).

- [ ] **Step 4: Переставить порядок «подрезать → экранировать»**

В `on_refine_publish` заменить блок от `variant_text = ...` до конца `try/except`:

```python
    variant_text = callback.message.text or ""
    pending_media = get_pending_media(db_path, telegram_id)

    # WHY подрезаем ДО экранирования: format_variant() превращает «&» в
    # «&amp;», и обрезка уже экранированной строки может разрубить сущность
    # пополам («&am»). Telegram отклоняет такое сообщение целиком, то есть
    # починка длины ломала публикацию вместо того, чтобы её спасать.
    # Подпись к медиа считается по разобранному тексту, поэтому мерять надо
    # именно чистый вариант.
    body = variant_text
    if pending_media is not None:
        body = post_length.trim(variant_text, post_length.TELEGRAM_CAPTION_LIMIT)
    formatted_text = output_formatter.format_variant(body)

    try:
        if pending_media is None:
            await bot.send_message(channel_id, formatted_text, parse_mode=output_formatter.PARSE_MODE)
        else:
            file_id, media_type = pending_media
            if media_type == "photo":
                await bot.send_photo(
                    channel_id,
                    photo=file_id,
                    caption=formatted_text,
                    parse_mode=output_formatter.PARSE_MODE,
                )
            else:
                await bot.send_video(
                    channel_id,
                    video=file_id,
                    caption=formatted_text,
                    parse_mode=output_formatter.PARSE_MODE,
                )
    except TelegramAPIError:
```

- [ ] **Step 5: Запустить тесты и убедиться, что они проходят**

Run: `python -m pytest tests/test_handlers_refine.py -q`
Expected: PASS.

- [ ] **Step 6: Прогнать весь набор**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Коммит**

```bash
git add bot/handlers/refine.py tests/test_handlers_refine.py
git commit -m "fix: trim the channel caption before HTML-escaping it

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Ручная проверка после реализации

Добавить в `docs/manual-checklist.md` и пройти на живом боте:

1. `/start` → «Создать пост сейчас» → кнопка показывает «📏 Объём поста: Средний».
2. Нажать её → три варианта, «Средний» помечен «✓» → выбрать «Короткий» → подтверждение и возврат на экран создания поста, кнопка теперь показывает «Короткий».
3. Отправить боту длинный текст → все три Telegram-варианта заметно короче прежних; VK-варианты прежней длины.
4. Под Telegram-вариантом нажать «Ещё» → новый вариант того же объёма.
5. Переключить объём на «Развёрнутый», сгенерировать, нажать «Короче» → вариант ощутимо короче предыдущего.
6. Сгенерировать картинку к развёрнутому посту и опубликовать в канал → подпись целая, заканчивается законченным предложением, ничего не потеряно на полуслове.
