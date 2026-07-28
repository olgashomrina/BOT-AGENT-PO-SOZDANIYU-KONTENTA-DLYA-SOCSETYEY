# Авторский пост из дайджеста — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После дайджеста добавить кнопку «СОЗДАЙ МОЙ АВТОРСКИЙ ПОСТ»: пользователь выбирает пункт дайджеста, отдаёт боту 5+ образцов своих постов, бот пишет варианты поста с хэштегами в его личном стиле.

**Architecture:** Новый роутер `bot/handlers/authorpost.py` со своей клавиатурой `bot/keyboards/authorpost.py`. Всё остальное переиспользуется: образцы стиля — существующая таблица `style_examples`, генерация — `content_generator.generate_variants()` с новым флагом `with_hashtags`, вывод — `content.send_variants()` с уже готовыми кнопками доработки. Список пунктов дайджеста передаётся через FSM-данные (`digest_items`), кнопка несёт только индекс.

**Tech Stack:** Python 3.14, aiogram 3, SQLite (`sqlite3` из stdlib), pytest + `pytest-asyncio`, `unittest.mock.AsyncMock`.

**Spec:** `docs/superpowers/specs/2026-07-28-authorpost-from-digest-design.md`

## Global Constraints

- **Все строки для пользователя — только через `get_string(key, lang)`.** Хардкод текста в хендлерах и клавиатурах запрещён.
- **Каждый новый ключ локализации добавляется во все 4 файла**: `bot/locales/ru.py`, `en.py`, `vi.py`, `zh.py`. `tests/test_localization.py::test_all_locales_have_identical_keys` падает при расхождении.
- **Порог образцов — 5**, потолок хранилища — 10. Константа `REQUIRED_EXAMPLES = 5` живёт в `bot/handlers/authorpost.py`, `MAX_EXAMPLES_PER_USER = 10` — в `bot/storage/style_examples.py`.
- **Максимальная длина одного образца — 2000 символов**, как в `/settov` (`bot.handlers.settov.MAX_EXAMPLE_LENGTH`). Переиспользовать эту константу, не заводить вторую.
- **`callback_data` не длиннее 64 байт** (жёсткий лимит Telegram). Отсюда индексы вместо заголовков.
- **Проверки вайтлиста и лимита — в каждом callback-хендлере, который зовёт AI.** Middleware в `bot/main.py` навешаны только на `dispatcher.message`, для `callback_query` они не работают. Использовать `_check_whitelist_or_reply` / `_check_limit_or_reply` из `bot/handlers/refine.py`.
- **Отвечать на callback через `_safe_answer(callback)`** из `bot/handlers/refine.py`, не через `callback.answer()`: после медленного вызова AI Telegram успевает протухнуть запрос.
- **Запуск тестов:** `python -m pytest` из корня проекта.
- **Коммиты** после каждой задачи, сообщения в существующем стиле (`feat:` / `fix:` / `refactor:` / `docs:`).

---

### Task 1: Флаг хэштегов в генераторе контента

Чистая функция, ни от чего не зависит — стартовая точка.

**Files:**
- Modify: `bot/services/content_generator.py`
- Test: `tests/test_content_generator.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `content_generator._HASHTAG_INSTRUCTION: str`
  - `build_prompt(source_text, platform, content_language, extra_instruction=None, style_examples=None, with_hashtags=False) -> str`
  - `generate_variants(source_text, platform, content_language, count=3, extra_instruction=None, style_examples=None, with_hashtags=False) -> list[str]`

- [ ] **Step 1: Написать падающие тесты**

Дописать в конец `tests/test_content_generator.py`:

```python
def test_build_prompt_includes_hashtag_instruction_when_requested():
    prompt = content_generator.build_prompt("текст", "telegram", "ru", with_hashtags=True)

    assert content_generator._HASHTAG_INSTRUCTION in prompt


def test_build_prompt_without_hashtags_is_unchanged_from_default():
    prompt = content_generator.build_prompt("текст", "telegram", "ru")

    assert prompt == content_generator.build_prompt(
        "текст", "telegram", "ru", with_hashtags=False
    )
    assert content_generator._HASHTAG_INSTRUCTION not in prompt


def test_build_prompt_combines_hashtags_with_style_examples():
    prompt = content_generator.build_prompt(
        "текст",
        "telegram",
        "ru",
        style_examples=["Мой старый пост."],
        with_hashtags=True,
    )

    assert content_generator._HASHTAG_INSTRUCTION in prompt
    assert "Мой старый пост." in prompt


@pytest.mark.asyncio
async def test_generate_variants_passes_hashtag_flag_into_prompt(monkeypatch):
    mock_generate = AsyncMock(return_value="вариант")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    await content_generator.generate_variants(
        "исходник", "telegram", "ru", count=1, with_hashtags=True
    )

    called_prompt = mock_generate.await_args.args[0]
    assert called_prompt == content_generator.build_prompt(
        "исходник", "telegram", "ru", with_hashtags=True
    )
    assert content_generator._HASHTAG_INSTRUCTION in called_prompt
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_content_generator.py -k hashtag -v`
Expected: FAIL — `AttributeError: module 'bot.services.content_generator' has no attribute '_HASHTAG_INSTRUCTION'`

- [ ] **Step 3: Добавить константу**

В `bot/services/content_generator.py` после блока `_TONE_INSTRUCTION` (строка ~52):

```python
# Hashtag instruction for the "authored post from digest" flow (see
# docs/superpowers/specs/2026-07-28-authorpost-from-digest-design.md).
# Opt-in via a flag rather than always-on: posts from the main content flow
# have never carried hashtags, and adding them there unasked would silently
# change output the user already relies on.
_HASHTAG_INSTRUCTION = (
    "End the post with 3-6 relevant hashtags on their own final line, "
    "written in the same language as the post itself."
)
```

- [ ] **Step 4: Прокинуть флаг в `build_prompt`**

Заменить целиком функцию `build_prompt`:

```python
def build_prompt(
    source_text: str,
    platform: Platform,
    content_language: str,
    extra_instruction: str | None = None,
    style_examples: list[str] | None = None,
    with_hashtags: bool = False,
) -> str:
    extra_line = f"{extra_instruction}\n" if extra_instruction else ""
    hashtag_line = f"{_HASHTAG_INSTRUCTION}\n" if with_hashtags else ""
    style_section = _build_style_section(style_examples)
    return (
        "You are a social media copywriter. Write ONE ready-to-publish social "
        "media post based on the source material below.\n"
        f"{_PLATFORM_INSTRUCTIONS[platform]}\n"
        f"{_TONE_INSTRUCTION}\n"
        f"Write the post in this language (ISO 639-1 code): {content_language}.\n"
        f"{extra_line}"
        f"{hashtag_line}"
        f"{style_section}"
        "Return only the post text itself, without any preamble, quotes or "
        "explanation.\n\n"
        f"Source material:\n{source_text}"
    )
```

- [ ] **Step 5: Прокинуть флаг в `generate_variants`**

Заменить сигнатуру и вызов `build_prompt` внутри `generate_variants`:

```python
async def generate_variants(
    source_text: str,
    platform: Platform,
    content_language: str,
    count: int = 3,
    extra_instruction: str | None = None,
    style_examples: list[str] | None = None,
    with_hashtags: bool = False,
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
    )
    variants = []
    for _ in range(count):
        variant = await ai_gateway.generate_text(prompt, temperature=_VARIANT_TEMPERATURE)
        variants.append(variant)
    return variants
```

- [ ] **Step 6: Прогнать весь файл тестов**

Run: `python -m pytest tests/test_content_generator.py -v`
Expected: PASS, все тесты (включая старые про `style_examples` — промпт без флага не изменился)

- [ ] **Step 7: Коммит**

```bash
git add bot/services/content_generator.py tests/test_content_generator.py
git commit -m "feat: add opt-in hashtag instruction to post generation"
```

---

### Task 2: Хранилище образцов — потолок 10 и очистка

**Files:**
- Modify: `bot/storage/style_examples.py`
- Test: `tests/test_storage_style_examples.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `style_examples.MAX_EXAMPLES_PER_USER == 10`
  - `clear_style_examples(db_path: str, telegram_id: int) -> None`

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_storage_style_examples.py` заменить строку импорта на:

```python
from bot.storage.style_examples import (
    MAX_EXAMPLES_PER_USER,
    add_style_example,
    clear_style_examples,
    get_style_examples,
)
```

и дописать в конец файла:

```python
def test_cap_allows_ten_examples():
    assert MAX_EXAMPLES_PER_USER == 10


def test_clear_style_examples_removes_all_for_user(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Первый")
    add_style_example(db_path, TELEGRAM_ID, "Второй")

    clear_style_examples(db_path, TELEGRAM_ID)

    assert get_style_examples(db_path, TELEGRAM_ID) == []


def test_clear_style_examples_leaves_other_users_untouched(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Пример пользователя А")
    add_style_example(db_path, OTHER_TELEGRAM_ID, "Пример пользователя Б")

    clear_style_examples(db_path, TELEGRAM_ID)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
    assert get_style_examples(db_path, OTHER_TELEGRAM_ID) == ["Пример пользователя Б"]


def test_clear_style_examples_is_safe_for_unknown_user(db_path):
    clear_style_examples(db_path, TELEGRAM_ID)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_storage_style_examples.py -v`
Expected: FAIL при сборке — `ImportError: cannot import name 'clear_style_examples'`

- [ ] **Step 3: Поднять потолок**

В `bot/storage/style_examples.py` заменить блок константы:

```python
# Plan.md Phase 14: "лимит на количество (старые вытесняются)" — keep only
# the most recent MAX_EXAMPLES_PER_USER examples per user, evicting older
# ones on every insert.
#
# Raised 5 -> 10 for the authored-post flow, which requires at least 5
# examples before it will write anything: a cap of exactly 5 would leave
# the user no room to add a better example without losing an existing one.
MAX_EXAMPLES_PER_USER = 10
```

- [ ] **Step 4: Добавить `clear_style_examples`**

В конец `bot/storage/style_examples.py`:

```python
def clear_style_examples(db_path: str, telegram_id: int) -> None:
    # Used by the authored-post flow's "загрузить новые образцы" branch:
    # without a wipe, new examples would merge with the old ones under the
    # same cap, and the user would get a voice blended from two eras of
    # their writing instead of the one they just supplied.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM style_examples WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 5: Прогнать тесты хранилища и зависимые**

Run: `python -m pytest tests/test_storage_style_examples.py tests/test_handlers_settov.py -v`
Expected: PASS — старые тесты написаны через `MAX_EXAMPLES_PER_USER`, а не через литерал 5, поэтому смена потолка их не ломает

- [ ] **Step 6: Коммит**

```bash
git add bot/storage/style_examples.py tests/test_storage_style_examples.py
git commit -m "feat: raise style example cap to 10 and add clear_style_examples"
```

---

### Task 3: Строки локализации

20 новых ключей в 4 файлах. Отдельной задачей, потому что от них зависят и клавиатуры, и хендлеры.

**Files:**
- Modify: `bot/locales/ru.py`, `bot/locales/en.py`, `bot/locales/vi.py`, `bot/locales/zh.py`
- Test: `tests/test_localization.py` (уже существует, менять не нужно)

**Interfaces:**
- Consumes: ничего
- Produces: ключи `authorpost_*`, доступные через `get_string(key, lang)`:
  `authorpost_button`, `authorpost_digest_expired`, `authorpost_choose_item`,
  `authorpost_item_chosen`, `authorpost_next_button`, `authorpost_saved_examples_intro`,
  `authorpost_use_saved_button`, `authorpost_new_samples_button`, `authorpost_samples_cleared`,
  `authorpost_samples_prompt`, `authorpost_samples_progress`, `authorpost_samples_enough`,
  `authorpost_samples_done_button`, `authorpost_sample_too_long`, `authorpost_sample_non_text`,
  `authorpost_choose_platform`, `authorpost_platform_telegram_button`,
  `authorpost_platform_vk_button`, `authorpost_platform_both_button`, `authorpost_generating`

- [ ] **Step 1: Добавить русские строки**

В `bot/locales/ru.py` вставить перед закрывающей скобкой словаря `STRINGS`:

```python
    "authorpost_button": "✍️ СОЗДАЙ МОЙ АВТОРСКИЙ ПОСТ",
    "authorpost_digest_expired": (
        "Этот дайджест уже устарел — соберите свежий, и кнопка авторского "
        "поста заработает снова."
    ),
    "authorpost_choose_item": "По какому пункту дайджеста написать пост?",
    "authorpost_item_chosen": "Отлично, берём: {item}",
    "authorpost_next_button": "Помогу тебе написать, жми дальше",
    "authorpost_saved_examples_intro": (
        "Я уже знаю ваш почерк — сохранено образцов: {count}. Писать пост "
        "по ним или загрузите свежие?"
    ),
    "authorpost_use_saved_button": "Писать сразу",
    "authorpost_new_samples_button": "Загрузить новые образцы",
    "authorpost_samples_cleared": "Старые образцы удалены. Присылайте новые.",
    "authorpost_samples_prompt": (
        "Вставьте образцы своих постов — не менее {required}. Присылайте их "
        "подряд, каждый отдельным сообщением, обычным текстом. По ним я "
        "считаю ваш личный почерк."
    ),
    "authorpost_samples_progress": "Принято {count} из {required}.",
    "authorpost_samples_enough": (
        "Принято {count} из {required} ✅ Образцов достаточно. Можно прислать "
        "ещё для точности или нажать кнопку."
    ),
    "authorpost_samples_done_button": "Готово, пиши пост",
    "authorpost_sample_too_long": (
        "Этот образец слишком длинный. Пришлите, пожалуйста, покороче "
        "(до 2000 символов)."
    ),
    "authorpost_sample_non_text": (
        "Пришлите, пожалуйста, образец обычным текстовым сообщением."
    ),
    "authorpost_choose_platform": "Куда пишем?",
    "authorpost_platform_telegram_button": "Telegram",
    "authorpost_platform_vk_button": "VK",
    "authorpost_platform_both_button": "И туда, и туда",
    "authorpost_generating": "Пишу авторский пост в вашем стиле...",
```

- [ ] **Step 2: Добавить английские строки**

В `bot/locales/en.py`, тем же местом:

```python
    "authorpost_button": "✍️ WRITE MY AUTHORED POST",
    "authorpost_digest_expired": (
        "This digest has expired — collect a fresh one and the authored "
        "post button will work again."
    ),
    "authorpost_choose_item": "Which digest item should the post be about?",
    "authorpost_item_chosen": "Great, going with: {item}",
    "authorpost_next_button": "I'll help you write it — tap to continue",
    "authorpost_saved_examples_intro": (
        "I already know your voice — saved examples: {count}. Write from "
        "those, or upload fresh ones?"
    ),
    "authorpost_use_saved_button": "Write now",
    "authorpost_new_samples_button": "Upload new examples",
    "authorpost_samples_cleared": "Old examples deleted. Send the new ones.",
    "authorpost_samples_prompt": (
        "Paste examples of your own posts — at least {required}. Send them "
        "one after another, one per message, as plain text. I'll read your "
        "personal writing voice from them."
    ),
    "authorpost_samples_progress": "Accepted {count} of {required}.",
    "authorpost_samples_enough": (
        "Accepted {count} of {required} ✅ That's enough. Send more for "
        "accuracy, or tap the button."
    ),
    "authorpost_samples_done_button": "Done, write the post",
    "authorpost_sample_too_long": (
        "This example is too long. Please send a shorter one (up to 2000 "
        "characters)."
    ),
    "authorpost_sample_non_text": (
        "Please send the example as a plain text message."
    ),
    "authorpost_choose_platform": "Where are we posting?",
    "authorpost_platform_telegram_button": "Telegram",
    "authorpost_platform_vk_button": "VK",
    "authorpost_platform_both_button": "Both",
    "authorpost_generating": "Writing an authored post in your voice...",
```

- [ ] **Step 3: Добавить вьетнамские строки**

В `bot/locales/vi.py`:

```python
    "authorpost_button": "✍️ VIẾT BÀI ĐĂNG CỦA RIÊNG TÔI",
    "authorpost_digest_expired": (
        "Bản tin này đã cũ — hãy tổng hợp bản tin mới, nút viết bài sẽ "
        "hoạt động trở lại."
    ),
    "authorpost_choose_item": "Viết bài về mục nào trong bản tin?",
    "authorpost_item_chosen": "Tuyệt, chọn mục: {item}",
    "authorpost_next_button": "Tôi sẽ giúp bạn viết — nhấn để tiếp tục",
    "authorpost_saved_examples_intro": (
        "Tôi đã biết văn phong của bạn — số ví dụ đã lưu: {count}. Viết "
        "theo chúng hay tải lên ví dụ mới?"
    ),
    "authorpost_use_saved_button": "Viết ngay",
    "authorpost_new_samples_button": "Tải lên ví dụ mới",
    "authorpost_samples_cleared": "Đã xóa ví dụ cũ. Hãy gửi ví dụ mới.",
    "authorpost_samples_prompt": (
        "Hãy dán các bài đăng của bạn — ít nhất {required} bài. Gửi lần "
        "lượt, mỗi bài một tin nhắn, dạng văn bản thường. Tôi sẽ đọc ra "
        "văn phong riêng của bạn."
    ),
    "authorpost_samples_progress": "Đã nhận {count} trên {required}.",
    "authorpost_samples_enough": (
        "Đã nhận {count} trên {required} ✅ Vậy là đủ. Gửi thêm cho chính "
        "xác hơn, hoặc nhấn nút."
    ),
    "authorpost_samples_done_button": "Xong, viết bài đi",
    "authorpost_sample_too_long": (
        "Ví dụ này quá dài. Vui lòng gửi một ví dụ ngắn hơn (tối đa 2000 "
        "ký tự)."
    ),
    "authorpost_sample_non_text": (
        "Vui lòng gửi ví dụ dưới dạng tin nhắn văn bản thường."
    ),
    "authorpost_choose_platform": "Đăng ở đâu?",
    "authorpost_platform_telegram_button": "Telegram",
    "authorpost_platform_vk_button": "VK",
    "authorpost_platform_both_button": "Cả hai",
    "authorpost_generating": "Đang viết bài theo văn phong của bạn...",
```

- [ ] **Step 4: Добавить китайские строки**

В `bot/locales/zh.py`:

```python
    "authorpost_button": "✍️ 撰写我的原创帖子",
    "authorpost_digest_expired": (
        "这份摘要已过期——请重新收集一份，原创帖子按钮就会再次可用。"
    ),
    "authorpost_choose_item": "要针对摘要中的哪一条撰写帖子？",
    "authorpost_item_chosen": "好的，就用这条：{item}",
    "authorpost_next_button": "我来帮您写，点击继续",
    "authorpost_saved_examples_intro": (
        "我已经了解您的文风——已保存示例：{count} 个。用它们来写，还是上传新的？"
    ),
    "authorpost_use_saved_button": "直接开写",
    "authorpost_new_samples_button": "上传新示例",
    "authorpost_samples_cleared": "旧示例已删除。请发送新的示例。",
    "authorpost_samples_prompt": (
        "请粘贴您自己的帖子示例——不少于 {required} 篇。请连续发送，"
        "每条消息一篇，使用纯文本。我会从中读出您的个人文风。"
    ),
    "authorpost_samples_progress": "已收到 {count} / {required}。",
    "authorpost_samples_enough": (
        "已收到 {count} / {required} ✅ 示例已经足够。可以再发几篇提高准确度，"
        "或直接点击按钮。"
    ),
    "authorpost_samples_done_button": "完成，开始写帖子",
    "authorpost_sample_too_long": (
        "这个示例太长了。请发送短一些的示例（不超过 2000 个字符）。"
    ),
    "authorpost_sample_non_text": "请以纯文本消息发送示例。",
    "authorpost_choose_platform": "发布到哪里？",
    "authorpost_platform_telegram_button": "Telegram",
    "authorpost_platform_vk_button": "VK",
    "authorpost_platform_both_button": "两个都要",
    "authorpost_generating": "正在用您的文风撰写原创帖子……",
```

- [ ] **Step 5: Проверить, что все локали совпадают по ключам**

Run: `python -m pytest tests/test_localization.py -v`
Expected: PASS, в частности `test_all_locales_have_identical_keys`

- [ ] **Step 6: Коммит**

```bash
git add bot/locales/
git commit -m "feat: add authored-post flow strings to all four locales"
```

---

### Task 4: Клавиатуры авторского поста

**Files:**
- Create: `bot/keyboards/authorpost.py`
- Modify: `bot/keyboards/start.py`
- Create: `tests/test_keyboards_authorpost.py`
- Modify: `tests/test_keyboards_start.py`

**Interfaces:**
- Consumes: ключи локализации из Task 3
- Produces:
  - `CALLBACK_START = "authorpost:start"`
  - `CALLBACK_ITEM_PREFIX = "authorpost:item"` (данные: `authorpost:item:<index>`, index с нуля)
  - `CALLBACK_NEXT = "authorpost:next"`
  - `CALLBACK_USE_SAVED = "authorpost:use_saved"`
  - `CALLBACK_NEW_SAMPLES = "authorpost:new_samples"`
  - `CALLBACK_SAMPLES_DONE = "authorpost:samples_done"`
  - `CALLBACK_PLATFORM_PREFIX = "authorpost:platform"` (данные: `authorpost:platform:telegram|vk|both`)
  - `build_item_choice_keyboard(item_count: int) -> InlineKeyboardMarkup` (без `lang`: подписи кнопок — цифры, локализовать нечего)
  - `build_next_step_keyboard(lang: str) -> InlineKeyboardMarkup`
  - `build_saved_examples_keyboard(lang: str) -> InlineKeyboardMarkup`
  - `build_samples_done_keyboard(lang: str) -> InlineKeyboardMarkup`
  - `build_platform_keyboard(lang: str) -> InlineKeyboardMarkup`
  - `build_digest_topic_keyboard(lang, has_saved_topic)` теперь возвращает 2 ряда

- [ ] **Step 1: Написать падающие тесты клавиатур**

Создать `tests/test_keyboards_authorpost.py`:

```python
from __future__ import annotations

from bot.keyboards.authorpost import (
    CALLBACK_ITEM_PREFIX,
    CALLBACK_NEW_SAMPLES,
    CALLBACK_NEXT,
    CALLBACK_PLATFORM_PREFIX,
    CALLBACK_SAMPLES_DONE,
    CALLBACK_USE_SAVED,
    build_item_choice_keyboard,
    build_next_step_keyboard,
    build_platform_keyboard,
    build_samples_done_keyboard,
    build_saved_examples_keyboard,
)
from bot.locales.loader import get_string


def test_item_choice_keyboard_has_one_button_per_item():
    keyboard = build_item_choice_keyboard(6)

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert len(buttons) == 6
    assert [button.text for button in buttons] == ["1", "2", "3", "4", "5", "6"]


def test_item_choice_keyboard_uses_zero_based_index_in_callback_data():
    keyboard = build_item_choice_keyboard(3)

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        f"{CALLBACK_ITEM_PREFIX}:0",
        f"{CALLBACK_ITEM_PREFIX}:1",
        f"{CALLBACK_ITEM_PREFIX}:2",
    ]


def test_item_choice_keyboard_wraps_at_four_per_row():
    keyboard = build_item_choice_keyboard(8)

    assert len(keyboard.inline_keyboard) == 2
    assert len(keyboard.inline_keyboard[0]) == 4
    assert len(keyboard.inline_keyboard[1]) == 4


def test_item_choice_keyboard_partial_last_row():
    keyboard = build_item_choice_keyboard(5)

    assert len(keyboard.inline_keyboard) == 2
    assert len(keyboard.inline_keyboard[1]) == 1


def test_item_choice_keyboard_is_empty_for_zero_items():
    keyboard = build_item_choice_keyboard(0)

    assert keyboard.inline_keyboard == []


def test_next_step_keyboard():
    keyboard = build_next_step_keyboard("en")

    assert keyboard.inline_keyboard[0][0].text == get_string("authorpost_next_button", "en")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_NEXT


def test_saved_examples_keyboard_offers_both_branches():
    keyboard = build_saved_examples_keyboard("ru")

    assert keyboard.inline_keyboard[0][0].text == get_string("authorpost_use_saved_button", "ru")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_USE_SAVED
    assert keyboard.inline_keyboard[1][0].text == get_string(
        "authorpost_new_samples_button", "ru"
    )
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_NEW_SAMPLES


def test_samples_done_keyboard():
    keyboard = build_samples_done_keyboard("vi")

    assert keyboard.inline_keyboard[0][0].text == get_string(
        "authorpost_samples_done_button", "vi"
    )
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_SAMPLES_DONE


def test_platform_keyboard_has_three_choices():
    keyboard = build_platform_keyboard("ru")

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        f"{CALLBACK_PLATFORM_PREFIX}:telegram",
        f"{CALLBACK_PLATFORM_PREFIX}:vk",
        f"{CALLBACK_PLATFORM_PREFIX}:both",
    ]
    assert buttons[0].text == get_string("authorpost_platform_telegram_button", "ru")
    assert buttons[1].text == get_string("authorpost_platform_vk_button", "ru")
    assert buttons[2].text == get_string("authorpost_platform_both_button", "ru")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_keyboards_authorpost.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.keyboards.authorpost'`

- [ ] **Step 3: Создать модуль клавиатур**

Создать `bot/keyboards/authorpost.py`:

```python
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

CALLBACK_START = "authorpost:start"
CALLBACK_ITEM_PREFIX = "authorpost:item"
CALLBACK_NEXT = "authorpost:next"
CALLBACK_USE_SAVED = "authorpost:use_saved"
CALLBACK_NEW_SAMPLES = "authorpost:new_samples"
CALLBACK_SAMPLES_DONE = "authorpost:samples_done"
CALLBACK_PLATFORM_PREFIX = "authorpost:platform"

# Four number buttons per row: Telegram renders inline rows edge-to-edge, and
# a digest tops out at 8 items (4 news + 3 papers + 1 methods summary), so
# this lays out as one or two tidy rows rather than a tall single column.
_ITEMS_PER_ROW = 4


def build_item_choice_keyboard(item_count: int) -> InlineKeyboardMarkup:
    # Buttons carry the item's zero-based index, never its title: Telegram
    # caps callback_data at 64 bytes and a news headline blows straight past
    # that. The titles themselves live in FSM data (see
    # bot/handlers/authorpost.py), keyed by this index.
    buttons = [
        InlineKeyboardButton(
            text=str(index + 1), callback_data=f"{CALLBACK_ITEM_PREFIX}:{index}"
        )
        for index in range(item_count)
    ]
    rows = [
        buttons[start : start + _ITEMS_PER_ROW]
        for start in range(0, len(buttons), _ITEMS_PER_ROW)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_next_step_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_next_button", lang),
                    callback_data=CALLBACK_NEXT,
                )
            ]
        ]
    )


def build_saved_examples_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_use_saved_button", lang),
                    callback_data=CALLBACK_USE_SAVED,
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_new_samples_button", lang),
                    callback_data=CALLBACK_NEW_SAMPLES,
                )
            ],
        ]
    )


def build_samples_done_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_samples_done_button", lang),
                    callback_data=CALLBACK_SAMPLES_DONE,
                )
            ]
        ]
    )


def build_platform_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_platform_telegram_button", lang),
                    callback_data=f"{CALLBACK_PLATFORM_PREFIX}:telegram",
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_platform_vk_button", lang),
                    callback_data=f"{CALLBACK_PLATFORM_PREFIX}:vk",
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_platform_both_button", lang),
                    callback_data=f"{CALLBACK_PLATFORM_PREFIX}:both",
                )
            ],
        ]
    )
```

- [ ] **Step 4: Прогнать тесты клавиатур**

Run: `python -m pytest tests/test_keyboards_authorpost.py -v`
Expected: PASS, 10 тестов

- [ ] **Step 5: Написать падающий тест второй кнопки под дайджестом**

Дописать в конец `tests/test_keyboards_start.py`:

```python
from bot.keyboards.authorpost import CALLBACK_START as CALLBACK_AUTHORPOST_START


def test_digest_topic_keyboard_includes_authorpost_button():
    keyboard = build_digest_topic_keyboard("ru", has_saved_topic=True)

    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[1][0].text == get_string("authorpost_button", "ru")
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_AUTHORPOST_START


def test_digest_topic_keyboard_includes_authorpost_button_without_saved_topic():
    keyboard = build_digest_topic_keyboard("en", has_saved_topic=False)

    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_AUTHORPOST_START
```

- [ ] **Step 6: Убедиться, что тест падает**

Run: `python -m pytest tests/test_keyboards_start.py -k authorpost -v`
Expected: FAIL — `IndexError: list index out of range` (у клавиатуры пока один ряд)

- [ ] **Step 7: Добавить вторую кнопку**

В `bot/keyboards/start.py` добавить импорт после существующих импортов:

```python
from bot.keyboards.authorpost import CALLBACK_START as CALLBACK_AUTHORPOST_START
```

и заменить `build_digest_topic_keyboard` целиком:

```python
def build_digest_topic_keyboard(lang: str, has_saved_topic: bool) -> InlineKeyboardMarkup:
    label_key = (
        "menu_digest_change_topic_button" if has_saved_topic else "menu_digest_write_topic_button"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string(label_key, lang),
                    callback_data=CALLBACK_DIGEST_SET_TOPIC,
                )
            ],
            # Offered even when the digest turned up empty: the button leads
            # to a "digest expired / collect a fresh one" reply rather than a
            # dead end, and keeping the keyboard shape constant means the
            # user's muscle memory for the button position always holds.
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_button", lang),
                    callback_data=CALLBACK_AUTHORPOST_START,
                )
            ],
        ]
    )
```

- [ ] **Step 8: Прогнать тесты клавиатур целиком**

Run: `python -m pytest tests/test_keyboards_start.py tests/test_keyboards_authorpost.py -v`
Expected: PASS

- [ ] **Step 9: Коммит**

```bash
git add bot/keyboards/authorpost.py bot/keyboards/start.py tests/test_keyboards_authorpost.py tests/test_keyboards_start.py
git commit -m "feat: add authored-post keyboards and digest button"
```

---

### Task 5: Пункты дайджеста в FSM

**Files:**
- Modify: `bot/services/digest.py`
- Modify: `bot/handlers/start.py:129-206`
- Test: `tests/test_services_digest.py`
- Test: `tests/test_handlers_start.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `digest.flatten_digest_items(result: DigestResult) -> list[str]`
  - FSM-данные после выдачи дайджеста содержат `digest_items: list[str]`
  - `on_menu_news_digest(callback, state, db_path)` — добавлен параметр `state`

- [ ] **Step 1: Написать падающий тест `flatten_digest_items`**

Дописать в конец `tests/test_services_digest.py`:

```python
def test_flatten_digest_items_orders_news_then_papers_then_methods():
    result = digest.DigestResult(
        topic="ИИ",
        news=[digest.DigestItem(title="Новость 1", url="https://n1")],
        papers=[digest.DigestItem(title="Статья 1", url="https://p1")],
        methods_summary="Новая методика X.",
    )

    assert digest.flatten_digest_items(result) == [
        "Новость 1",
        "Статья 1",
        "Новая методика X.",
    ]


def test_flatten_digest_items_omits_absent_methods_summary():
    result = digest.DigestResult(
        topic="ИИ",
        news=[digest.DigestItem(title="Новость 1", url="https://n1")],
        papers=[],
        methods_summary=None,
    )

    assert digest.flatten_digest_items(result) == ["Новость 1"]


def test_flatten_digest_items_empty_for_empty_result():
    result = digest.DigestResult(topic="ИИ", news=[], papers=[], methods_summary=None)

    assert digest.flatten_digest_items(result) == []
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python -m pytest tests/test_services_digest.py -k flatten -v`
Expected: FAIL — `AttributeError: module 'bot.services.digest' has no attribute 'flatten_digest_items'`

- [ ] **Step 3: Реализовать `flatten_digest_items`**

В `bot/services/digest.py` после `format_digest_message` добавить:

```python
def flatten_digest_items(result: DigestResult) -> list[str]:
    # One flat, index-addressable list matching the order the user sees in
    # format_digest_message() — news, then papers, then the synthesized
    # methods paragraph. The authored-post flow numbers its buttons off this
    # list, so the two orderings must never drift apart.
    #
    # News and papers contribute their title only, not the URL: the title is
    # what the model writes the post about, and a Google News redirect URL is
    # 400-900 chars of noise in the prompt.
    items = [item.title for item in result.news]
    items.extend(item.title for item in result.papers)
    if result.methods_summary:
        items.append(result.methods_summary)
    return items
```

- [ ] **Step 4: Прогнать тесты сервиса**

Run: `python -m pytest tests/test_services_digest.py -v`
Expected: PASS

- [ ] **Step 5: Написать падающие тесты хендлеров**

`tests/test_handlers_start.py` уже содержит хелперы `_make_message(telegram_id, language_code, text="/start")` и `_make_state(telegram_id)` — переиспользовать их, новых не заводить.

Расширить импорт из `bot.handlers.start` до:

```python
from bot.handlers.start import cmd_help, cmd_start, on_digest_topic_input, on_menu_news_digest
```

и дописать в конец файла:

```python
from bot.services import digest as digest_service
from bot.storage.users import set_digest_topic
from bot.storage.whitelist import add_user


# on_menu_news_digest goes through _check_limit_or_reply, which calls
# load_settings() — without these the whole test errors on missing env.
@pytest.fixture
def _settings_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


def _sample_digest_result():
    return digest_service.DigestResult(
        topic="ИИ",
        news=[digest_service.DigestItem(title="Новость 1", url="https://n1")],
        papers=[digest_service.DigestItem(title="Статья 1", url="https://p1")],
        methods_summary="Новая методика X.",
    )


def _make_digest_callback(telegram_id: int):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_menu_news_digest_stores_items_in_fsm(db_path, monkeypatch, _settings_env):
    telegram_id = 555
    add_user(db_path, telegram_id)
    set_digest_topic(db_path, telegram_id, "ИИ")
    monkeypatch.setattr(
        digest_service, "build_digest", AsyncMock(return_value=_sample_digest_result())
    )
    state = _make_state(telegram_id)

    await on_menu_news_digest(_make_digest_callback(telegram_id), state, db_path)

    data = await state.get_data()
    assert data["digest_items"] == ["Новость 1", "Статья 1", "Новая методика X."]


@pytest.mark.asyncio
async def test_digest_topic_input_stores_items_in_fsm(db_path, monkeypatch):
    telegram_id = 556
    add_user(db_path, telegram_id)
    monkeypatch.setattr(
        digest_service, "build_digest", AsyncMock(return_value=_sample_digest_result())
    )
    state = _make_state(telegram_id)
    message = _make_message(telegram_id, "ru", text="ИИ")

    await on_digest_topic_input(message, state, db_path)

    data = await state.get_data()
    assert data["digest_items"] == ["Новость 1", "Статья 1", "Новая методика X."]
```

В шапке файла к существующим импортам добавить `from unittest.mock import ANY, AsyncMock, call` → уже есть; убедиться, что `SimpleNamespace` импортирован (он есть).

- [ ] **Step 6: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_handlers_start.py -k "stores_items" -v`
Expected: FAIL — `TypeError: on_menu_news_digest() takes 2 positional arguments but 3 were given`

- [ ] **Step 7: Записывать пункты в FSM в `on_menu_news_digest`**

В `bot/handlers/start.py` добавить импорт `flatten_digest_items` не нужен — обращаться через `digest.flatten_digest_items`. Заменить хендлер целиком:

```python
@router.callback_query(F.data == CALLBACK_NEWS_DIGEST)
async def on_menu_news_digest(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    topic = get_digest_topic(db_path, telegram_id)
    if topic is None:
        await callback.message.answer(
            get_string("digest_prompt_no_topic", language),
            reply_markup=build_digest_topic_keyboard(language, has_saved_topic=False),
        )
        await _safe_answer(callback)
        return

    if not await _check_limit_or_reply(callback, db_path, language):
        return

    result = await digest.build_digest(topic)
    increment_usage(db_path, telegram_id)

    # Stash the digest's items for the authored-post flow
    # (bot/handlers/authorpost.py): its number buttons carry only an index,
    # because a headline never fits Telegram's 64-byte callback_data.
    await state.update_data(digest_items=digest.flatten_digest_items(result))

    await callback.message.answer(digest.format_digest_message(result, language))
    await callback.message.answer(
        get_string("digest_change_topic_prompt", language),
        reply_markup=build_digest_topic_keyboard(language, has_saved_topic=True),
    )
    await _safe_answer(callback)
```

- [ ] **Step 8: Записывать пункты в FSM в `on_digest_topic_input`**

Там же заменить хвост хендлера `on_digest_topic_input` (начиная со строки `result = await digest.build_digest(topic)`):

```python
    result = await digest.build_digest(topic)
    await state.update_data(digest_items=digest.flatten_digest_items(result))

    await message.answer(digest.format_digest_message(result, language))
    await message.answer(
        get_string("digest_change_topic_prompt", language),
        reply_markup=build_digest_topic_keyboard(language, has_saved_topic=True),
    )
```

Важно: `await state.set_state(None)` выше по хендлеру остаётся на месте — сбрасывается состояние, а не данные, они независимы.

- [ ] **Step 9: Прогнать тесты**

Run: `python -m pytest tests/test_handlers_start.py tests/test_services_digest.py -v`
Expected: PASS

- [ ] **Step 10: Коммит**

```bash
git add bot/services/digest.py bot/handlers/start.py tests/test_services_digest.py tests/test_handlers_start.py
git commit -m "feat: stash digest items in FSM for the authored-post flow"
```

---

### Task 6: Публичная `send_variants` и сброс флага хэштегов

**Files:**
- Modify: `bot/handlers/content.py:229-235`, `bot/handlers/content.py:249`
- Test: `tests/test_handlers_content_flow.py`

**Interfaces:**
- Consumes: `content_generator.generate_variants(..., with_hashtags=...)` из Task 1
- Produces:
  - `content.send_variants(message, language, platform, variants) -> None`
  - FSM-данные после обычной генерации содержат `with_hashtags=False`

- [ ] **Step 1: Написать падающий тест сброса флага**

Дописать в конец `tests/test_handlers_content_flow.py` (хелперы `_make_state`, `_make_message`, `_make_bot`, `_mock_generate_variants` в файле уже есть — использовать их; `_make_message` сам выставляет `photo`/`video`/`voice` в `None`, поэтому сообщение не уедет в ветку медиавложения):

```python
from bot.handlers import content as content_module


@pytest.mark.asyncio
async def test_normal_generation_resets_hashtag_flag(db_path, monkeypatch):
    state = _make_state()
    # Simulate leftovers from an earlier authored-post run in the same chat.
    await state.update_data(with_hashtags=True)
    _mock_generate_variants(monkeypatch)
    message = _make_message(text="Исходный текст")

    await route_content(message, db_path, _make_bot(), state)

    data = await state.get_data()
    assert data["with_hashtags"] is False


def test_send_variants_is_public():
    assert hasattr(content_module, "send_variants")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_handlers_content_flow.py -k "hashtag_flag or send_variants_is_public" -v`
Expected: FAIL — `AssertionError` (нет атрибута `send_variants`) и `KeyError: 'with_hashtags'`

- [ ] **Step 3: Сделать `send_variants` публичной**

В `bot/handlers/content.py` заменить определение:

```python
# Public because bot/handlers/authorpost.py sends its variants through the
# same path — same formatting, same refine keyboard — and duplicating this
# there would let the two output formats drift apart.
async def send_variants(message: Message, language: str, platform: str, variants: list[str]) -> None:
    for index, variant in enumerate(variants, start=1):
        await message.answer(
            output_formatter.format_variant(variant),
            parse_mode=output_formatter.PARSE_MODE,
            reply_markup=build_refine_keyboard(platform, index, language),
        )
```

и заменить оба вызова в конце `_finish`:

```python
    await send_variants(message, language, "telegram", telegram_variants)
    await send_variants(message, language, "vk", vk_variants)
```

- [ ] **Step 4: Сбрасывать флаг хэштегов**

В `bot/handlers/content.py` в `_finish` заменить строку `await state.update_data(...)`:

```python
    # with_hashtags is written explicitly, not merely left alone: FSM data
    # persists per chat, so a True left over from an earlier authored-post
    # run would make bot/handlers/refine.py bolt hashtags onto ordinary
    # posts the user never asked to tag.
    await state.update_data(
        source_text=text,
        content_language=content_language,
        language=language,
        with_hashtags=False,
    )
```

- [ ] **Step 5: Прогнать тесты**

Run: `python -m pytest tests/test_handlers_content_flow.py -v`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add bot/handlers/content.py tests/test_handlers_content_flow.py
git commit -m "refactor: make send_variants public and reset hashtag flag in main flow"
```

---

### Task 7: Доработка сохраняет стиль и хэштеги

Чинит существующее поведение: кнопка «Ещё вариант» сегодня возвращает текст без авторского стиля, хотя исходные варианты были в стиле.

**Files:**
- Modify: `bot/handlers/refine.py:89-137`
- Test: `tests/test_handlers_refine.py`

**Interfaces:**
- Consumes: `content_generator.generate_variants(..., style_examples=..., with_hashtags=...)` из Task 1
- Produces: ничего нового; меняется вызов внутри `_generate_and_send`

- [ ] **Step 1: Обновить существующие тесты и добавить новые**

В `tests/test_handlers_refine.py` найти `test_refine_more_generates_and_sends_new_variant` и заменить его assert на:

```python
    mock_generate.assert_awaited_once_with(
        "Исходный текст статьи.",
        "telegram",
        "ru",
        count=1,
        extra_instruction=None,
        style_examples=[],
        with_hashtags=False,
    )
```

Найти аналогичный assert в тесте про `on_refine_shorten` и добавить в него те же два аргумента (`extra_instruction` там остаётся `SHORTEN_INSTRUCTION`).

Дописать в конец файла:

```python
from bot.storage.style_examples import add_style_example


@pytest.mark.asyncio
async def test_refine_more_forwards_stored_style_examples(db_path, monkeypatch):
    add_style_example(db_path, TELEGRAM_ID, "Мой старый пост.")
    state = _make_state()
    await _seed_finished_session(state)
    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    await on_refine_more(_make_callback(data="refine:more:telegram:1"), state, db_path)

    assert mock_generate.await_args.kwargs["style_examples"] == ["Мой старый пост."]


@pytest.mark.asyncio
async def test_refine_more_forwards_hashtag_flag_from_fsm(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state)
    await state.update_data(with_hashtags=True)
    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    await on_refine_more(_make_callback(data="refine:more:telegram:1"), state, db_path)

    assert mock_generate.await_args.kwargs["with_hashtags"] is True


@pytest.mark.asyncio
async def test_refine_more_defaults_hashtag_flag_to_false(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state)
    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    await on_refine_more(_make_callback(data="refine:more:telegram:1"), state, db_path)

    assert mock_generate.await_args.kwargs["with_hashtags"] is False
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_handlers_refine.py -k "style_examples or hashtag" -v`
Expected: FAIL — `KeyError: 'style_examples'` (аргумент пока не передаётся)

- [ ] **Step 3: Передавать стиль и флаг при перегенерации**

В `bot/handlers/refine.py` добавить импорт после существующих:

```python
from bot.storage.style_examples import get_style_examples
```

и в `_generate_and_send` заменить блок вызова генератора:

```python
    # WHY read these here rather than trusting the caller: "Ещё вариант" and
    # "Короче" must produce a post indistinguishable in voice from the batch
    # they sit under. Before this, refine called generate_variants() with
    # neither the user's style examples nor the hashtag flag, so one tap on
    # "Короче" silently stripped the personal voice off an authored post.
    style_examples = get_style_examples(db_path, telegram_id)
    with_hashtags = bool(data.get("with_hashtags"))

    try:
        variants = await content_generator.generate_variants(
            source_text,
            platform,
            content_language,
            count=1,
            extra_instruction=extra_instruction,
            style_examples=style_examples,
            with_hashtags=with_hashtags,
        )
```

- [ ] **Step 4: Прогнать тесты**

Run: `python -m pytest tests/test_handlers_refine.py -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add bot/handlers/refine.py tests/test_handlers_refine.py
git commit -m "fix: keep author voice and hashtags when refining a variant"
```

---

### Task 8: Роутер авторского поста — выбор пункта дайджеста

**Files:**
- Create: `bot/handlers/authorpost.py`
- Create: `tests/test_handlers_authorpost.py`

**Interfaces:**
- Consumes: клавиатуры из Task 4, строки из Task 3, `digest_items` в FSM из Task 5
- Produces:
  - `authorpost.router: Router` (name=`"authorpost"`)
  - `authorpost.REQUIRED_EXAMPLES == 5`
  - `AuthorPostStates.collecting_examples`
  - `on_authorpost_start(callback, state, db_path)`
  - `on_authorpost_item(callback, state, db_path)`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_handlers_authorpost.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.authorpost import on_authorpost_item, on_authorpost_start
from bot.keyboards.authorpost import CALLBACK_ITEM_PREFIX, CALLBACK_START
from bot.locales.loader import get_string
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111

DIGEST_ITEMS = [
    "Новость про ИИ",
    "Вторая новость",
    "Научная статья",
    "Новая методика X.",
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_callback(data: str, telegram_id: int = TELEGRAM_ID):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.data = data
    callback.message = AsyncMock()
    return callback


def _make_message(text: str | None = None, telegram_id: int = TELEGRAM_ID):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    message.text = text
    return message


@pytest.mark.asyncio
async def test_start_shows_one_button_per_digest_item(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_choose_item", "ru")
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert len(buttons) == len(DIGEST_ITEMS)


@pytest.mark.asyncio
async def test_start_reports_expired_digest_when_fsm_has_no_items(db_path):
    state = _make_state()
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")


@pytest.mark.asyncio
async def test_start_reports_expired_digest_when_items_are_empty(db_path):
    state = _make_state()
    await state.update_data(digest_items=[])
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")


@pytest.mark.asyncio
async def test_start_refuses_user_outside_whitelist(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(CALLBACK_START, telegram_id=999)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("error_not_whitelisted", "ru")


@pytest.mark.asyncio
async def test_item_choice_stores_source_text_and_offers_next_step(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:2")

    await on_authorpost_item(callback, state, db_path)

    data = await state.get_data()
    assert data["source_text"] == "Научная статья"
    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_item_chosen", "ru", item="Научная статья")
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_item_choice_out_of_range_reports_expired_digest(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:99")

    await on_authorpost_item(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
    data = await state.get_data()
    assert "source_text" not in data


@pytest.mark.asyncio
async def test_item_choice_without_digest_items_reports_expired(db_path):
    state = _make_state()
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:0")

    await on_authorpost_item(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_handlers_authorpost.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.handlers.authorpost'`

- [ ] **Step 3: Создать роутер с выбором пункта**

Создать `bot/handlers/authorpost.py`:

```python
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery

from bot.handlers.content import _resolve_language
from bot.handlers.refine import _check_whitelist_or_reply, _safe_answer
from bot.keyboards.authorpost import (
    CALLBACK_ITEM_PREFIX,
    CALLBACK_START,
    build_item_choice_keyboard,
    build_next_step_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="authorpost")

# Below this many stored style examples the bot refuses to write: fewer
# samples do not carry a recognisable voice, they just bias the model toward
# whichever single post it saw.
REQUIRED_EXAMPLES = 5


class AuthorPostStates(StatesGroup):
    # Only one state, and only for the sample-collection step, which is the
    # one place this flow has to intercept ordinary text messages. Every
    # other step is a callback_query with unique callback_data. A state left
    # set outside this step would be actively harmful: route_content in
    # bot/handlers/content.py filters on StateFilter(None), so the bot would
    # stop reacting to normal messages entirely.
    collecting_examples = State()


async def _report_expired_digest(callback: CallbackQuery, language: str) -> None:
    # Reached when FSM data has no digest items — most often because the bot
    # process restarted (storage is in-memory MemoryStorage, see
    # bot/main.py), but also when a button from a previous digest is tapped
    # after a newer, shorter digest replaced the list.
    await callback.message.answer(get_string("authorpost_digest_expired", language))
    await _safe_answer(callback)


@router.callback_query(F.data == CALLBACK_START)
async def on_authorpost_start(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    data = await state.get_data()
    items = data.get("digest_items") or []
    if not items:
        await _report_expired_digest(callback, language)
        return

    await callback.message.answer(
        get_string("authorpost_choose_item", language),
        reply_markup=build_item_choice_keyboard(len(items)),
    )
    await _safe_answer(callback)


@router.callback_query(F.data.startswith(f"{CALLBACK_ITEM_PREFIX}:"))
async def on_authorpost_item(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    data = await state.get_data()
    items = data.get("digest_items") or []
    index = int(callback.data.rsplit(":", 1)[1])
    if index >= len(items):
        await _report_expired_digest(callback, language)
        return

    item = items[index]
    # source_text is the same FSM key bot/handlers/refine.py reads, so the
    # "Ещё / Короче" buttons under the generated variants work with no extra
    # wiring on this side.
    await state.update_data(source_text=item)
    logger.info(
        "Authored post source selected",
        extra={"user_id": telegram_id, "operation": "handler:authorpost", "item_index": index},
    )

    await callback.message.answer(
        get_string("authorpost_item_chosen", language, item=item),
        reply_markup=build_next_step_keyboard(language),
    )
    await _safe_answer(callback)
```

- [ ] **Step 4: Прогнать тесты**

Run: `python -m pytest tests/test_handlers_authorpost.py -v`
Expected: PASS, 7 тестов

- [ ] **Step 5: Коммит**

```bash
git add bot/handlers/authorpost.py tests/test_handlers_authorpost.py
git commit -m "feat: add authored-post router with digest item selection"
```

---

### Task 9: Сбор образцов стиля

**Files:**
- Modify: `bot/handlers/authorpost.py`
- Test: `tests/test_handlers_authorpost.py`

**Interfaces:**
- Consumes: `REQUIRED_EXAMPLES`, `AuthorPostStates` из Task 8; `clear_style_examples` из Task 2
- Produces:
  - `on_authorpost_next(callback, state, db_path)`
  - `on_authorpost_use_saved(callback, db_path)`
  - `on_authorpost_new_samples(callback, state, db_path)`
  - `on_authorpost_sample(message, state, db_path)`
  - `on_authorpost_samples_done(callback, state, db_path)`

- [ ] **Step 1: Написать падающие тесты**

Дописать в конец `tests/test_handlers_authorpost.py`:

```python
from bot.handlers.authorpost import (
    REQUIRED_EXAMPLES,
    AuthorPostStates,
    on_authorpost_new_samples,
    on_authorpost_next,
    on_authorpost_sample,
    on_authorpost_samples_done,
    on_authorpost_use_saved,
)
from bot.handlers.settov import MAX_EXAMPLE_LENGTH
from bot.storage.style_examples import add_style_example, get_style_examples


@pytest.mark.asyncio
async def test_next_step_prompts_for_samples_when_storage_empty(db_path):
    state = _make_state()
    callback = _make_callback("authorpost:next")

    await on_authorpost_next(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_samples_prompt", "ru", required=REQUIRED_EXAMPLES)
    assert await state.get_state() == AuthorPostStates.collecting_examples.state


@pytest.mark.asyncio
async def test_next_step_offers_saved_examples_when_enough_stored(db_path):
    for index in range(REQUIRED_EXAMPLES):
        add_style_example(db_path, TELEGRAM_ID, f"Пост {index}")
    state = _make_state()
    callback = _make_callback("authorpost:next")

    await on_authorpost_next(callback, state, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string(
        "authorpost_saved_examples_intro", "ru", count=REQUIRED_EXAMPLES
    )
    assert "reply_markup" in kwargs
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_next_step_prompts_for_samples_when_stored_below_threshold(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Единственный пост")
    state = _make_state()
    callback = _make_callback("authorpost:next")

    await on_authorpost_next(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_samples_prompt", "ru", required=REQUIRED_EXAMPLES)


@pytest.mark.asyncio
async def test_use_saved_goes_straight_to_platform_choice(db_path):
    callback = _make_callback("authorpost:use_saved")

    await on_authorpost_use_saved(callback, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_choose_platform", "ru")
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_new_samples_wipes_storage_and_starts_collecting(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Старый пост")
    state = _make_state()
    callback = _make_callback("authorpost:new_samples")

    await on_authorpost_new_samples(callback, state, db_path)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
    assert await state.get_state() == AuthorPostStates.collecting_examples.state


@pytest.mark.asyncio
async def test_sample_below_threshold_shows_progress_without_done_button(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text="Мой пост")

    await on_authorpost_sample(message, state, db_path)

    args, kwargs = message.answer.call_args
    assert args[0] == get_string(
        "authorpost_samples_progress", "ru", count=1, required=REQUIRED_EXAMPLES
    )
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_sample_at_threshold_offers_done_button(db_path):
    for index in range(REQUIRED_EXAMPLES - 1):
        add_style_example(db_path, TELEGRAM_ID, f"Пост {index}")
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text="Пятый пост")

    await on_authorpost_sample(message, state, db_path)

    args, kwargs = message.answer.call_args
    assert args[0] == get_string(
        "authorpost_samples_enough", "ru", count=REQUIRED_EXAMPLES, required=REQUIRED_EXAMPLES
    )
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_sample_counter_includes_previously_stored_examples(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Ранее сохранённый")
    add_style_example(db_path, TELEGRAM_ID, "И ещё один")
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text="Третий")

    await on_authorpost_sample(message, state, db_path)

    args, _ = message.answer.call_args
    assert args[0] == get_string(
        "authorpost_samples_progress", "ru", count=3, required=REQUIRED_EXAMPLES
    )


@pytest.mark.asyncio
async def test_non_text_sample_is_rejected_without_counting(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text=None)

    await on_authorpost_sample(message, state, db_path)

    args, _ = message.answer.call_args
    assert args[0] == get_string("authorpost_sample_non_text", "ru")
    assert get_style_examples(db_path, TELEGRAM_ID) == []


@pytest.mark.asyncio
async def test_overlong_sample_is_rejected_without_counting(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text="я" * (MAX_EXAMPLE_LENGTH + 1))

    await on_authorpost_sample(message, state, db_path)

    args, _ = message.answer.call_args
    assert args[0] == get_string("authorpost_sample_too_long", "ru")
    assert get_style_examples(db_path, TELEGRAM_ID) == []


@pytest.mark.asyncio
async def test_samples_done_clears_state_and_asks_for_platform(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    callback = _make_callback("authorpost:samples_done")

    await on_authorpost_samples_done(callback, state, db_path)

    assert await state.get_state() is None
    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_choose_platform", "ru")
    assert "reply_markup" in kwargs
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_handlers_authorpost.py -v`
Expected: FAIL при сборке — `ImportError: cannot import name 'on_authorpost_next'`

- [ ] **Step 3: Дополнить импорты роутера**

В `bot/handlers/authorpost.py` заменить блок импортов на:

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.handlers.content import _resolve_language
from bot.handlers.refine import _check_whitelist_or_reply, _safe_answer
from bot.handlers.settov import MAX_EXAMPLE_LENGTH
from bot.keyboards.authorpost import (
    CALLBACK_ITEM_PREFIX,
    CALLBACK_NEW_SAMPLES,
    CALLBACK_NEXT,
    CALLBACK_SAMPLES_DONE,
    CALLBACK_START,
    CALLBACK_USE_SAVED,
    build_item_choice_keyboard,
    build_next_step_keyboard,
    build_platform_keyboard,
    build_samples_done_keyboard,
    build_saved_examples_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.storage.style_examples import (
    add_style_example,
    clear_style_examples,
    get_style_examples,
)
```

- [ ] **Step 4: Добавить хендлеры сбора образцов**

В конец `bot/handlers/authorpost.py`:

```python
async def _ask_for_samples(callback: CallbackQuery, state: FSMContext, language: str) -> None:
    await state.set_state(AuthorPostStates.collecting_examples)
    await callback.message.answer(
        get_string("authorpost_samples_prompt", language, required=REQUIRED_EXAMPLES)
    )
    await _safe_answer(callback)


async def _ask_for_platform(callback: CallbackQuery, language: str) -> None:
    await callback.message.answer(
        get_string("authorpost_choose_platform", language),
        reply_markup=build_platform_keyboard(language),
    )
    await _safe_answer(callback)


def _stored_example_count(db_path: str, telegram_id: int) -> int:
    return len(get_style_examples(db_path, telegram_id))


@router.callback_query(F.data == CALLBACK_NEXT)
async def on_authorpost_next(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    count = _stored_example_count(db_path, telegram_id)
    if count >= REQUIRED_EXAMPLES:
        await callback.message.answer(
            get_string("authorpost_saved_examples_intro", language, count=count),
            reply_markup=build_saved_examples_keyboard(language),
        )
        await _safe_answer(callback)
        return

    await _ask_for_samples(callback, state, language)


@router.callback_query(F.data == CALLBACK_USE_SAVED)
async def on_authorpost_use_saved(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await _ask_for_platform(callback, language)


@router.callback_query(F.data == CALLBACK_NEW_SAMPLES)
async def on_authorpost_new_samples(
    callback: CallbackQuery, state: FSMContext, db_path: str
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    # Wipe rather than append: leaving the old examples in would blend two
    # eras of the user's writing under one cap, and "загрузить новые" would
    # quietly mean "загрузить ещё".
    clear_style_examples(db_path, telegram_id)
    await callback.message.answer(get_string("authorpost_samples_cleared", language))
    await _ask_for_samples(callback, state, language)


@router.message(AuthorPostStates.collecting_examples)
async def on_authorpost_sample(message: Message, state: FSMContext, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    if not message.text:
        await message.answer(get_string("authorpost_sample_non_text", language))
        return

    if len(message.text) > MAX_EXAMPLE_LENGTH:
        await message.answer(get_string("authorpost_sample_too_long", language))
        return

    add_style_example(db_path, telegram_id, message.text)
    # The counter reports everything in storage, not just this session's
    # messages: "не менее 5" means "the bot holds 5 samples of your voice",
    # so a user who already had 2 saved is done after 3 more.
    count = _stored_example_count(db_path, telegram_id)

    if count >= REQUIRED_EXAMPLES:
        await message.answer(
            get_string(
                "authorpost_samples_enough", language, count=count, required=REQUIRED_EXAMPLES
            ),
            reply_markup=build_samples_done_keyboard(language),
        )
        return

    await message.answer(
        get_string("authorpost_samples_progress", language, count=count, required=REQUIRED_EXAMPLES)
    )


@router.callback_query(F.data == CALLBACK_SAMPLES_DONE, AuthorPostStates.collecting_examples)
async def on_authorpost_samples_done(
    callback: CallbackQuery, state: FSMContext, db_path: str
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    # Back to None before anything else: while a state is set, route_content
    # (StateFilter(None)) never fires and the bot ignores ordinary messages.
    await state.set_state(None)
    await _ask_for_platform(callback, language)
```

- [ ] **Step 5: Прогнать тесты**

Run: `python -m pytest tests/test_handlers_authorpost.py -v`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add bot/handlers/authorpost.py tests/test_handlers_authorpost.py
git commit -m "feat: collect style samples in the authored-post flow"
```

---

### Task 10: Выбор площадки и генерация

**Files:**
- Modify: `bot/handlers/authorpost.py`
- Test: `tests/test_handlers_authorpost.py`

**Interfaces:**
- Consumes: `content.send_variants` из Task 6, `generate_variants(..., with_hashtags=...)` из Task 1, `build_platform_keyboard` из Task 4
- Produces: `on_authorpost_platform(callback, state, db_path)`

- [ ] **Step 1: Написать падающие тесты**

Дописать в конец `tests/test_handlers_authorpost.py`:

```python
from bot.handlers.authorpost import on_authorpost_platform
from bot.services import content_generator
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.limits import get_daily_count


async def _seed_ready_session(state: FSMContext, db_path: str) -> None:
    for index in range(REQUIRED_EXAMPLES):
        add_style_example(db_path, TELEGRAM_ID, f"Пост {index}")
    await state.update_data(
        digest_items=DIGEST_ITEMS,
        source_text="Научная статья",
        content_language="ru",
        language="ru",
    )
    await state.set_state(None)


@pytest.mark.asyncio
async def test_platform_telegram_generates_with_style_and_hashtags(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    mock_generate = AsyncMock(return_value=["Вариант 1", "Вариант 2", "Вариант 3"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:telegram")

    await on_authorpost_platform(callback, state, db_path)

    mock_generate.assert_awaited_once()
    kwargs = mock_generate.await_args.kwargs
    assert mock_generate.await_args.args[1] == "telegram"
    assert kwargs["with_hashtags"] is True
    assert len(kwargs["style_examples"]) == REQUIRED_EXAMPLES


@pytest.mark.asyncio
async def test_platform_both_generates_for_two_platforms(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    mock_generate = AsyncMock(return_value=["Вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:both")

    await on_authorpost_platform(callback, state, db_path)

    platforms = [call.args[1] for call in mock_generate.await_args_list]
    assert platforms == ["telegram", "vk"]


@pytest.mark.asyncio
async def test_platform_choice_sets_hashtag_flag_in_fsm(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    monkeypatch.setattr(
        content_generator, "generate_variants", AsyncMock(return_value=["Вариант"])
    )
    callback = _make_callback("authorpost:platform:vk")

    await on_authorpost_platform(callback, state, db_path)

    data = await state.get_data()
    assert data["with_hashtags"] is True


@pytest.mark.asyncio
async def test_platform_choice_without_source_reports_expired(db_path, monkeypatch):
    state = _make_state()
    mock_generate = AsyncMock(return_value=["Вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:telegram")

    await on_authorpost_platform(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
    mock_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_choice_refuses_user_outside_whitelist(db_path, monkeypatch):
    state = _make_state(telegram_id=999)
    mock_generate = AsyncMock(return_value=["Вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:telegram", telegram_id=999)

    await on_authorpost_platform(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("error_not_whitelisted", "ru")
    mock_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_choice_reports_ai_error_without_spending_quota(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    monkeypatch.setattr(
        content_generator,
        "generate_variants",
        AsyncMock(side_effect=AIGatewayTimeoutError("timed out")),
    )
    callback = _make_callback("authorpost:platform:telegram")

    await on_authorpost_platform(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("error_ai_timeout", "ru")
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_platform_choice_spends_quota_on_success(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    monkeypatch.setattr(
        content_generator, "generate_variants", AsyncMock(return_value=["Вариант"])
    )
    callback = _make_callback("authorpost:platform:telegram")

    await on_authorpost_platform(callback, state, db_path)

    assert get_daily_count(db_path, TELEGRAM_ID) == 1
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_handlers_authorpost.py -k platform -v`
Expected: FAIL при сборке — `ImportError: cannot import name 'on_authorpost_platform'`

- [ ] **Step 3: Дополнить импорты**

В `bot/handlers/authorpost.py` добавить к существующим импортам:

```python
from bot.config import load_settings
from bot.handlers.content import _AI_ERROR_KEYS, _resolve_language, send_variants
from bot.handlers.refine import (
    _check_limit_or_reply,
    _check_whitelist_or_reply,
    _safe_answer,
)
from bot.keyboards.authorpost import CALLBACK_PLATFORM_PREFIX  # к существующему блоку
from bot.services import content_generator
from bot.services.ai_gateway import AIGatewayError
from bot.storage.limits import increment_usage
from bot.storage.users import get_content_language
```

Существующую строку `from bot.handlers.content import _resolve_language` заменить объединённой версией выше; существующую строку импорта из `bot.handlers.refine` — тоже.

- [ ] **Step 4: Добавить хендлер площадки и генерации**

В конец `bot/handlers/authorpost.py`:

```python
# callback_data suffix -> the platforms to generate for, in output order.
_PLATFORM_TARGETS: dict[str, tuple[str, ...]] = {
    "telegram": ("telegram",),
    "vk": ("vk",),
    "both": ("telegram", "vk"),
}


@router.callback_query(F.data.startswith(f"{CALLBACK_PLATFORM_PREFIX}:"))
async def on_authorpost_platform(
    callback: CallbackQuery, state: FSMContext, db_path: str
) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    source_text = data.get("source_text")
    if not source_text:
        await _report_expired_digest(callback, language)
        return

    if not await _check_limit_or_reply(callback, db_path, language):
        return

    platforms = _PLATFORM_TARGETS[callback.data.rsplit(":", 1)[1]]
    content_language = data.get("content_language") or get_content_language(
        db_path, telegram_id
    ) or language
    settings = load_settings()
    style_examples = get_style_examples(db_path, telegram_id)

    # Recorded so bot/handlers/refine.py keeps the hashtags when the user
    # taps "Ещё"/"Короче" under one of these variants.
    await state.update_data(
        source_text=source_text, content_language=content_language, with_hashtags=True
    )

    await callback.message.answer(get_string("authorpost_generating", language))

    generated: list[tuple[str, list[str]]] = []
    for platform in platforms:
        try:
            variants = await content_generator.generate_variants(
                source_text,
                platform,
                content_language,
                count=settings.content_variants_count,
                style_examples=style_examples,
                with_hashtags=True,
            )
        except AIGatewayError as exc:
            error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
            logger.warning(
                "AI Gateway error during authored post generation",
                extra={
                    "user_id": telegram_id,
                    "operation": "authorpost_generate",
                    "error_class": type(exc).__name__,
                },
            )
            await callback.message.answer(get_string(error_key, language))
            await _safe_answer(callback)
            return
        generated.append((platform, variants))

    # One usage unit per platform, charged only after every call succeeded:
    # a failed generation above returns early and costs the user nothing,
    # matching how bot/handlers/refine.py bills its own regenerations.
    for _ in platforms:
        increment_usage(db_path, telegram_id)

    for platform, variants in generated:
        await send_variants(callback.message, language, platform, variants)

    await _safe_answer(callback)
```

- [ ] **Step 5: Прогнать тесты**

Run: `python -m pytest tests/test_handlers_authorpost.py -v`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add bot/handlers/authorpost.py tests/test_handlers_authorpost.py
git commit -m "feat: generate authored post variants with hashtags per platform"
```

---

### Task 11: Регистрация роутера и ручной чек-лист

**Files:**
- Modify: `bot/main.py:11-18`, `bot/main.py:42-52`
- Modify: `tests/conftest.py:5-35`
- Modify: `docs/manual-checklist.md`
- Test: `tests/test_main_site_api_wiring.py`

**Interfaces:**
- Consumes: `authorpost.router` из Task 8
- Produces: рабочий сценарий в живом боте

- [ ] **Step 1: Написать падающий тест регистрации**

Дописать в конец `tests/test_main_site_api_wiring.py`:

```python
def test_dispatcher_includes_authorpost_router():
    from bot.handlers.authorpost import router as authorpost_router
    from bot.main import build_dispatcher

    dispatcher = build_dispatcher(daily_limit=10, monthly_limit=100)

    assert authorpost_router in dispatcher.sub_routers
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python -m pytest tests/test_main_site_api_wiring.py -k authorpost -v`
Expected: FAIL — `AssertionError`

- [ ] **Step 3: Зарегистрировать роутер**

В `bot/main.py` добавить импорт в алфавитном порядке, первым в блоке `bot.handlers`:

```python
from bot.handlers.authorpost import router as authorpost_router
```

и в `build_dispatcher` вставить строку после `settov_router`:

```python
    dispatcher.include_router(settov_router)
    # Before content_router: its message handler is state-filtered to
    # AuthorPostStates.collecting_examples, and keeping the state-specific
    # router ahead of content_router's catch-all StateFilter(None) matches
    # how settov_router is already ordered.
    dispatcher.include_router(authorpost_router)
    dispatcher.include_router(content_router)
```

- [ ] **Step 4: Добавить роутер в conftest**

В `tests/conftest.py` добавить импорт:

```python
from bot.handlers.authorpost import router as authorpost_router
```

и в кортеж `_SINGLETON_ROUTERS` добавить `authorpost_router` после `settov_router`. Обновить комментарий над кортежем: «The 8 module-level singleton routers» → «The 9 module-level singleton routers».

- [ ] **Step 5: Прогнать весь набор тестов**

Run: `python -m pytest`
Expected: PASS, все тесты зелёные

- [ ] **Step 6: Дописать ручной чек-лист**

В конец `docs/manual-checklist.md` добавить раздел:

```markdown
## Авторский пост из дайджеста

- [ ] Собрать дайджест → под ним две кнопки: «Собрать дайджест по другой теме» и «✍️ СОЗДАЙ МОЙ АВТОРСКИЙ ПОСТ»
- [ ] Нажать авторский пост → пришёл ряд кнопок с номерами, их количество совпадает с числом пунктов в дайджесте
- [ ] Нажать номер → бот назвал выбранный пункт и предложил «Помогу тебе написать, жми дальше»
- [ ] Нажать «дальше» с пустым хранилищем → просьба прислать не менее 5 образцов
- [ ] Прислать 5 постов подряд → счётчик рос 1→5, на пятом появилась кнопка «Готово, пиши пост»
- [ ] Выбрать Telegram → пришло 3 варианта, **в каждом есть хэштеги**
- [ ] **Варианты звучат как присланные образцы**, а не как обезличенный текст (проверяется только глазами)
- [ ] Нажать «Короче» под вариантом → сокращённый текст сохранил и стиль, и хэштеги
- [ ] Повторно пройти сценарий → бот предложил «Писать сразу / Загрузить новые образцы»
- [ ] Выбрать «Загрузить новые» → счётчик начался с нуля
- [ ] Перезапустить бота, затем нажать кнопку авторского поста под старым дайджестом → сообщение «дайджест устарел», без зависания
- [ ] Обычная генерация (прислать боту ссылку/текст) → в вариантах **нет** хэштегов
```

- [ ] **Step 7: Коммит**

```bash
git add bot/main.py tests/conftest.py tests/test_main_site_api_wiring.py docs/manual-checklist.md
git commit -m "feat: wire authored-post router and add manual checklist"
```

---

## Проверка после всех задач

- [ ] `python -m pytest` — весь набор зелёный
- [ ] Пройти ручной чек-лист из `docs/manual-checklist.md` на живом боте
