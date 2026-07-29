# Realistic Photo Upgrade Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "🎨 Сделать реалистичнее (~15₽)" button under every AI-generated image that lets the user pay to regenerate it with the premium `img-flux/pro1.1` model, without changing the free/cheap default generation.

**Architecture:** The cheap image (already implemented in `bot/handlers/refine.py::on_refine_image` and `bot/handlers/start.py::on_photo_gen_description`) gets a new one-button inline keyboard attached to its `send_photo` call. The prompt used to generate it is stashed in FSM state (`last_image_prompt`) because by the time the button is clicked, the original post/description text is no longer on screen. A single new callback handler (`img:upgrade`), shared by both flows, re-runs `ai_gateway.generate_image()` with a separate premium model config value, sends the result as a second message, and disables the button on the original message so it can't be clicked twice.

**Tech Stack:** Python 3.12, aiogram 3, pytest + pytest-asyncio (existing stack, no new dependencies).

## Global Constraints

- Follow the design in `docs/superpowers/specs/2026-07-29-realistic-photo-upgrade-design.md` exactly — no confirmation dialog, no dynamic pricing, price is a hardcoded "~15₽" in the button label.
- Both existing image-generation flows (`refine.py`, `start.py`) must get the button — do not scope this to only one.
- The upgraded photo is sent as a **new** message; the original cheap photo and its message are never edited or deleted, only its keyboard changes.
- Reuse existing patterns exactly: `_AI_ERROR_KEYS` for error mapping, `_check_whitelist_or_reply`/`_check_limit_or_reply`/`_safe_answer` from `bot/handlers/refine.py`, `set_pending_media`/`increment_usage` calls in the same shape as the existing image handlers.
- All 4 locale files (`ru`, `en`, `vi`, `zh`) get every new string — don't leave any locale falling back to Russian.

---

### Task 1: Premium image model config

**Files:**
- Modify: `bot/config.py:24-25` (constants), `bot/config.py` `Settings` dataclass (`ai_gateway_image_size` field), `bot/config.py::load_settings` (env read + return), `.env.example:52-57`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.ai_gateway_premium_image_model: str`, read from env var `AI_GATEWAY_PREMIUM_IMAGE_MODEL`, defaulting to `"img-flux/pro1.1"`. Consumed by Task 5's handler via `load_settings().ai_gateway_premium_image_model`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py` (after `test_load_settings_reads_optional_overrides`, following the same pattern as that test):

```python
def test_load_settings_premium_image_model_defaults_to_flux_pro(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("AI_GATEWAY_PREMIUM_IMAGE_MODEL", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.ai_gateway_premium_image_model == "img-flux/pro1.1"


def test_load_settings_premium_image_model_reads_from_env(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"AI_GATEWAY_PREMIUM_IMAGE_MODEL": "img-flux/kontext-max"})

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.ai_gateway_premium_image_model == "img-flux/kontext-max"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -k premium_image_model -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'ai_gateway_premium_image_model'` (or `TypeError` from `load_settings` env handling, since the attribute doesn't exist yet).

- [ ] **Step 3: Add the constant, field, and env read**

In `bot/config.py`, change:

```python
DEFAULT_AI_GATEWAY_IMAGE_MODEL = "img-flux/flux-2-klein-4b"
DEFAULT_AI_GATEWAY_IMAGE_SIZE = "1024x1024"
```

to:

```python
DEFAULT_AI_GATEWAY_IMAGE_MODEL = "img-flux/flux-2-klein-4b"
DEFAULT_AI_GATEWAY_IMAGE_SIZE = "1024x1024"
# Separate from AI_GATEWAY_IMAGE_MODEL so the "Сделать реалистичнее" upgrade
# button (bot/handlers/refine.py::on_image_upgrade) keeps working regardless
# of which model the default (cheap) generation is pinned to.
DEFAULT_AI_GATEWAY_PREMIUM_IMAGE_MODEL = "img-flux/pro1.1"
```

In the `Settings` dataclass, add a field right after `ai_gateway_image_size: str`:

```python
    ai_gateway_image_size: str
    ai_gateway_premium_image_model: str
```

In `load_settings()`, right after the line `ai_gateway_image_size = os.environ.get("AI_GATEWAY_IMAGE_SIZE", DEFAULT_AI_GATEWAY_IMAGE_SIZE)`, add:

```python
    ai_gateway_premium_image_model = os.environ.get(
        "AI_GATEWAY_PREMIUM_IMAGE_MODEL", DEFAULT_AI_GATEWAY_PREMIUM_IMAGE_MODEL
    )
```

In the `return Settings(...)` call, add the field right after `ai_gateway_image_size=ai_gateway_image_size,`:

```python
        ai_gateway_image_size=ai_gateway_image_size,
        ai_gateway_premium_image_model=ai_gateway_premium_image_model,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: all PASS (including the two new tests and every pre-existing one — `Settings` is a dataclass, adding a required field with no default is safe here because every call site builds it via the keyword-argument constructor in `load_settings`, not positionally).

- [ ] **Step 5: Document the new env var**

In `.env.example`, right after the `AI_GATEWAY_IMAGE_MODEL` block (around line 57), add:

```
# Модель для кнопки "Сделать реалистичнее" под уже сгенерированной картинкой.
# Необязательно, по умолчанию img-flux/pro1.1 (FLUX1.1 Pro, ~15₽/картинку —
# отдельно от тарифа "Профессиональный", списывается с баланса счёта).
AI_GATEWAY_PREMIUM_IMAGE_MODEL=img-flux/pro1.1
```

- [ ] **Step 6: Commit**

```bash
git add bot/config.py .env.example tests/test_config.py
git commit -m "feat: add separate config for premium image upgrade model"
```

---

### Task 2: Locale strings

**Files:**
- Modify: `bot/locales/ru.py:186` (after `image_attached_confirmation` block), `bot/locales/en.py` (equivalent block), `bot/locales/vi.py` (equivalent block), `bot/locales/zh.py` (equivalent block)

**Interfaces:**
- Produces: locale keys `image_upgrade_button`, `image_upgraded_button`, `image_upgraded_caption` in all 4 files, fetched via `get_string(key, lang)` (Task 3 and Task 5 consume these).

- [ ] **Step 1: Add strings to `bot/locales/ru.py`**

Find this block (around line 179-186):

```python
    "generate_image_button": "🖼 Картинка от ИИ",
    "image_preview_caption": "Превью картинки от ИИ",
    "image_delivery_failed": "Не получилось отправить картинку — попробуйте ещё раз чуть позже.",
    "image_attached_confirmation": (
        "Картинка от ИИ готова и прикреплена — она будет использована при "
        "следующей публикации в канал. Чтобы убрать вложение, используйте "
        "команду /clear_media."
    ),
```

Add immediately after the closing `),` of `image_attached_confirmation`:

```python
    "image_upgrade_button": "🎨 Сделать реалистичнее (~15₽)",
    "image_upgraded_button": "✅ Готово",
    "image_upgraded_caption": "✨ Более реалистичная версия",
```

- [ ] **Step 2: Add strings to `bot/locales/en.py`**

Find the equivalent block (around line 175-181, `generate_image_button` through `image_attached_confirmation`) and add immediately after it:

```python
    "image_upgrade_button": "🎨 Make it more realistic (~15₽)",
    "image_upgraded_button": "✅ Done",
    "image_upgraded_caption": "✨ More realistic version",
```

- [ ] **Step 3: Add strings to `bot/locales/vi.py`**

Find the equivalent block (around line 178-184) and add immediately after it:

```python
    "image_upgrade_button": "🎨 Làm ảnh chân thực hơn (~15₽)",
    "image_upgraded_button": "✅ Xong",
    "image_upgraded_caption": "✨ Phiên bản chân thực hơn",
```

- [ ] **Step 4: Add strings to `bot/locales/zh.py`**

Find the equivalent block (around line 134-140) and add immediately after it:

```python
    "image_upgrade_button": "🎨 生成更逼真的照片 (~15₽)",
    "image_upgraded_button": "✅ 完成",
    "image_upgraded_caption": "✨ 更逼真的版本",
```

- [ ] **Step 5: Verify every locale loads without error**

Run: `python -c "from bot.locales.loader import get_string; [print(get_string(k, l)) for l in ('ru','en','vi','zh') for k in ('image_upgrade_button','image_upgraded_button','image_upgraded_caption')]"`
Expected: 12 lines printed, no `KeyError`.

- [ ] **Step 6: Commit**

```bash
git add bot/locales/ru.py bot/locales/en.py bot/locales/vi.py bot/locales/zh.py
git commit -m "feat: add locale strings for realistic-photo upgrade button"
```

---

### Task 3: Keyboard builders

**Files:**
- Modify: `bot/keyboards/refine.py`
- Test: `tests/test_keyboards_refine.py`

**Interfaces:**
- Consumes: `get_string(key, lang)` from `bot.locales.loader` (already imported in this file).
- Produces: `CALLBACK_IMAGE_UPGRADE = "img:upgrade"`, `CALLBACK_IMAGE_UPGRADE_DONE = "img:upgrade:done"`, `build_image_upgrade_keyboard(lang: str) -> InlineKeyboardMarkup`, `build_image_upgraded_keyboard(lang: str) -> InlineKeyboardMarkup`. Consumed by Task 4 (`refine.py`, `start.py` handlers) and Task 5 (new handlers).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_keyboards_refine.py`:

```python
from bot.keyboards.refine import (
    CALLBACK_IMAGE_UPGRADE,
    CALLBACK_IMAGE_UPGRADE_DONE,
    build_image_upgrade_keyboard,
    build_image_upgraded_keyboard,
)


def test_image_upgrade_keyboard_has_single_button_with_price_in_label():
    keyboard = build_image_upgrade_keyboard("ru")

    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    button = keyboard.inline_keyboard[0][0]
    assert button.text == get_string("image_upgrade_button", "ru")
    assert button.callback_data == CALLBACK_IMAGE_UPGRADE


def test_image_upgraded_keyboard_has_single_disabled_style_button():
    keyboard = build_image_upgraded_keyboard("ru")

    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    button = keyboard.inline_keyboard[0][0]
    assert button.text == get_string("image_upgraded_button", "ru")
    assert button.callback_data == CALLBACK_IMAGE_UPGRADE_DONE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_keyboards_refine.py -v`
Expected: FAIL with `ImportError: cannot import name 'CALLBACK_IMAGE_UPGRADE'`.

- [ ] **Step 3: Implement the keyboard builders**

In `bot/keyboards/refine.py`, add after the existing `CALLBACK_SITE_PUSH_PREFIX = "site:push"` line:

```python
CALLBACK_IMAGE_UPGRADE = "img:upgrade"
CALLBACK_IMAGE_UPGRADE_DONE = "img:upgrade:done"
```

At the end of the file, after `build_refine_keyboard`, add:

```python
def build_image_upgrade_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("image_upgrade_button", lang),
                    callback_data=CALLBACK_IMAGE_UPGRADE,
                )
            ]
        ]
    )


def build_image_upgraded_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("image_upgraded_button", lang),
                    callback_data=CALLBACK_IMAGE_UPGRADE_DONE,
                )
            ]
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_keyboards_refine.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/keyboards/refine.py tests/test_keyboards_refine.py
git commit -m "feat: add keyboard builders for realistic-photo upgrade button"
```

---

### Task 4: Attach the upgrade button to both existing image flows

**Files:**
- Modify: `bot/handlers/refine.py` (`on_refine_image`, imports)
- Modify: `bot/handlers/start.py` (`on_photo_gen_description`, imports)
- Test: `tests/test_handlers_refine.py`, `tests/test_handlers_start.py`

**Interfaces:**
- Consumes: `build_image_upgrade_keyboard(lang: str)` from Task 3.
- Produces: both flows now call `state.update_data(last_image_prompt=...)` before generating the image, and attach `reply_markup=build_image_upgrade_keyboard(language)` to the `bot.send_photo(...)` call. Task 5's handler reads `data.get("last_image_prompt")`.

- [ ] **Step 1: Write the failing test for `on_refine_image`**

Add to `tests/test_handlers_refine.py`, right after `test_refine_image_success_stores_telegram_file_id`:

```python
@pytest.mark.asyncio
async def test_refine_image_success_attaches_upgrade_button_and_stores_prompt(db_path, monkeypatch):
    from bot.keyboards.refine import build_image_upgrade_keyboard

    state = _make_state()
    await _seed_finished_session(state)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_refine_image(callback, state, db_path, bot)

    _, kwargs = bot.send_photo.call_args
    expected_keyboard = build_image_upgrade_keyboard("ru")
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        expected_keyboard.inline_keyboard[0][0].callback_data
    )
    assert (await state.get_data())["last_image_prompt"] == "a vivid english prompt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handlers_refine.py -k attaches_upgrade_button -v`
Expected: FAIL — `kwargs["reply_markup"]` is `None` (no `reply_markup` passed yet) and/or `KeyError: 'last_image_prompt'`.

- [ ] **Step 3: Update `on_refine_image` in `bot/handlers/refine.py`**

Add to the import block at the top:

```python
from bot.keyboards.refine import build_image_upgrade_keyboard, build_refine_keyboard
```

(replacing the existing `from bot.keyboards.refine import build_refine_keyboard` line).

Change:

```python
    try:
        image_prompt = await content_generator.generate_image_prompt(post_text)
        image_bytes = await ai_gateway.generate_image(image_prompt)
    except AIGatewayError as exc:
```

to:

```python
    try:
        image_prompt = await content_generator.generate_image_prompt(post_text)
        await state.update_data(last_image_prompt=image_prompt)
        image_bytes = await ai_gateway.generate_image(image_prompt)
    except AIGatewayError as exc:
```

Change:

```python
    try:
        sent_message = await bot.send_photo(
            callback.message.chat.id,
            photo=BufferedInputFile(image_bytes, filename="ai_image.png"),
            caption=get_string("image_preview_caption", language),
        )
```

to:

```python
    try:
        sent_message = await bot.send_photo(
            callback.message.chat.id,
            photo=BufferedInputFile(image_bytes, filename="ai_image.png"),
            caption=get_string("image_preview_caption", language),
            reply_markup=build_image_upgrade_keyboard(language),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_handlers_refine.py -v`
Expected: all PASS, including the pre-existing `on_refine_image` tests (they don't assert on `reply_markup`, so adding it doesn't break them) and the new one.

- [ ] **Step 5: Write the failing test for `on_photo_gen_description`**

Add to `tests/test_handlers_start.py`, right after `test_photo_gen_description_generates_and_attaches_image`:

```python
@pytest.mark.asyncio
async def test_photo_gen_description_attaches_upgrade_button_and_stores_prompt(db_path, monkeypatch):
    from bot.keyboards.refine import build_image_upgrade_keyboard

    add_user(db_path, 3005)
    state = _make_state(3005)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    message = _make_description_message(3005, "горы на рассвете")
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_photo_gen_description(message, state, db_path, bot)

    _, kwargs = bot.send_photo.call_args
    expected_keyboard = build_image_upgrade_keyboard("ru")
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        expected_keyboard.inline_keyboard[0][0].callback_data
    )
    assert (await state.get_data())["last_image_prompt"] == "a vivid english prompt"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest tests/test_handlers_start.py -k attaches_upgrade_button -v`
Expected: FAIL, same shape of failure as Step 2.

- [ ] **Step 7: Update `on_photo_gen_description` in `bot/handlers/start.py`**

Add to the imports:

```python
from bot.keyboards.refine import build_image_upgrade_keyboard
```

Change:

```python
    try:
        image_prompt = await content_generator.generate_image_prompt(description)
        image_bytes = await ai_gateway.generate_image(image_prompt)
    except AIGatewayError as exc:
```

to:

```python
    try:
        image_prompt = await content_generator.generate_image_prompt(description)
        await state.update_data(last_image_prompt=image_prompt)
        image_bytes = await ai_gateway.generate_image(image_prompt)
    except AIGatewayError as exc:
```

Change:

```python
    try:
        sent_message = await bot.send_photo(
            message.chat.id,
            photo=BufferedInputFile(image_bytes, filename="ai_image.png"),
            caption=get_string("image_preview_caption", language),
        )
```

to:

```python
    try:
        sent_message = await bot.send_photo(
            message.chat.id,
            photo=BufferedInputFile(image_bytes, filename="ai_image.png"),
            caption=get_string("image_preview_caption", language),
            reply_markup=build_image_upgrade_keyboard(language),
        )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_handlers_start.py -v`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add bot/handlers/refine.py bot/handlers/start.py tests/test_handlers_refine.py tests/test_handlers_start.py
git commit -m "feat: attach realistic-photo upgrade button to generated images"
```

---

### Task 5: The upgrade handler itself

**Files:**
- Modify: `bot/handlers/refine.py` (new handlers, imports)
- Test: `tests/test_handlers_refine.py`

**Interfaces:**
- Consumes: `CALLBACK_IMAGE_UPGRADE`, `CALLBACK_IMAGE_UPGRADE_DONE`, `build_image_upgraded_keyboard` (Task 3); `Settings.ai_gateway_premium_image_model` (Task 1); `data["last_image_prompt"]` (Task 4).
- Produces: `on_image_upgrade(callback, state, db_path, bot)` and `on_image_upgrade_done(callback)`, registered on `router` for `F.data == CALLBACK_IMAGE_UPGRADE` / `F.data == CALLBACK_IMAGE_UPGRADE_DONE`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_handlers_refine.py`, at the end of the file:

```python
from bot.handlers.refine import on_image_upgrade, on_image_upgrade_done
from bot.keyboards.refine import CALLBACK_IMAGE_UPGRADE, build_image_upgraded_keyboard


async def _seed_upgrade_session(state: FSMContext, prompt: str = "a vivid english prompt") -> None:
    await state.update_data(language="ru", last_image_prompt=prompt)
    await state.set_state(None)


@pytest.mark.asyncio
async def test_image_upgrade_success_uses_premium_model_and_sends_new_photo(db_path, monkeypatch):
    state = _make_state()
    await _seed_upgrade_session(state)

    mock_generate_image = AsyncMock(return_value=b"fake-premium-png-bytes")
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.message.edit_reply_markup = AsyncMock()
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("premium-file-id"))

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_awaited_once_with("a vivid english prompt", model="img-flux/pro1.1")
    bot.send_photo.assert_awaited_once()
    args, kwargs = bot.send_photo.call_args
    assert args[0] == TELEGRAM_ID
    assert kwargs["photo"].data == b"fake-premium-png-bytes"
    assert kwargs["caption"] == get_string("image_upgraded_caption", "ru")

    assert get_pending_media(db_path, TELEGRAM_ID) == ("premium-file-id", "photo")
    assert get_daily_count(db_path, TELEGRAM_ID) == 1

    callback.message.edit_reply_markup.assert_awaited_once()
    _, edit_kwargs = callback.message.edit_reply_markup.call_args
    expected_keyboard = build_image_upgraded_keyboard("ru")
    assert edit_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        expected_keyboard.inline_keyboard[0][0].callback_data
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_upgrade_ai_error_replies_friendly_message_and_keeps_button(db_path, monkeypatch):
    state = _make_state()
    await _seed_upgrade_session(state)

    mock_generate_image = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.message.edit_reply_markup = AsyncMock()
    bot = AsyncMock()

    await on_image_upgrade(callback, state, db_path, bot)

    bot.send_photo.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    callback.message.edit_reply_markup.assert_not_awaited()
    assert get_pending_media(db_path, TELEGRAM_ID) is None
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_image_upgrade_missing_prompt_replies_friendly_error_and_does_not_call_ai(db_path, monkeypatch):
    state = _make_state()
    await state.update_data(language="ru")
    await state.set_state(None)

    mock_generate_image = AsyncMock()
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_refine_missing_context", "ru"))


@pytest.mark.asyncio
async def test_image_upgrade_blocked_when_not_whitelisted_does_not_call_ai(db_path, monkeypatch):
    NOT_WHITELISTED_ID = 998
    state = _make_state(NOT_WHITELISTED_ID)
    await _seed_upgrade_session(state)

    mock_generate_image = AsyncMock()
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=NOT_WHITELISTED_ID)
    bot = AsyncMock()

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_image_upgrade_delivery_failure_replies_friendly_error_and_does_not_attach_or_charge(
    db_path, monkeypatch
):
    state = _make_state()
    await _seed_upgrade_session(state)

    mock_generate_image = AsyncMock(return_value=b"fake-premium-png-bytes")
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.message.edit_reply_markup = AsyncMock()
    bot = AsyncMock()
    bot.send_photo = AsyncMock(
        side_effect=TelegramBadRequest(
            method=SendMessage(chat_id=TELEGRAM_ID, text="x"), message="failed to fetch image"
        )
    )

    await on_image_upgrade(callback, state, db_path, bot)

    callback.message.answer.assert_awaited_once_with(get_string("image_delivery_failed", "ru"))
    callback.message.edit_reply_markup.assert_not_awaited()
    assert get_pending_media(db_path, TELEGRAM_ID) is None
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_image_upgrade_done_button_just_acknowledges(db_path):
    callback = _make_callback(data="img:upgrade:done")

    await on_image_upgrade_done(callback)

    callback.answer.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handlers_refine.py -k image_upgrade -v`
Expected: FAIL with `ImportError: cannot import name 'on_image_upgrade'`.

- [ ] **Step 3: Implement the handlers**

In `bot/handlers/refine.py`, update the keyboard import (already changed in Task 4) to also bring in the new names:

```python
from bot.keyboards.refine import (
    CALLBACK_IMAGE_UPGRADE,
    CALLBACK_IMAGE_UPGRADE_DONE,
    build_image_upgrade_keyboard,
    build_image_upgraded_keyboard,
    build_refine_keyboard,
)
```

At the end of the file, after `on_refine_image`, add:

```python
@router.callback_query(F.data == CALLBACK_IMAGE_UPGRADE)
async def on_image_upgrade(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    if not await _check_limit_or_reply(callback, db_path, language):
        return

    image_prompt = data.get("last_image_prompt")
    if not image_prompt:
        await callback.message.answer(get_string("error_refine_missing_context", language))
        await _safe_answer(callback)
        return

    settings = load_settings()

    try:
        image_bytes = await ai_gateway.generate_image(
            image_prompt, model=settings.ai_gateway_premium_image_model
        )
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during image upgrade",
            extra={
                "user_id": telegram_id,
                "operation": "generate_image_upgrade",
                "error_class": type(exc).__name__,
            },
        )
        await callback.message.answer(get_string(error_key, language))
        await _safe_answer(callback)
        return

    try:
        sent_message = await bot.send_photo(
            callback.message.chat.id,
            photo=BufferedInputFile(image_bytes, filename="ai_image_upgraded.png"),
            caption=get_string("image_upgraded_caption", language),
        )
    except TelegramAPIError:
        logger.warning(
            "Failed to deliver upgraded image to user",
            extra={"user_id": telegram_id, "operation": "generate_image_upgrade"},
        )
        await callback.message.answer(get_string("image_delivery_failed", language))
        await _safe_answer(callback)
        return

    increment_usage(db_path, telegram_id)

    file_id = sent_message.photo[-1].file_id
    set_pending_media(db_path, telegram_id, file_id, "photo")

    # WHY swallow TelegramBadRequest here specifically: same "stale
    # callback" class of failure as _safe_answer below — the upgraded photo
    # has already been delivered and billed by this point, so a cosmetic
    # failure to disable the now-redundant button must not surface as an
    # error to the user.
    try:
        await callback.message.edit_reply_markup(reply_markup=build_image_upgraded_keyboard(language))
    except TelegramBadRequest as exc:
        logger.warning(
            "Failed to replace image-upgrade button (likely stale)", extra={"error_message": str(exc)}
        )

    await _safe_answer(callback)


@router.callback_query(F.data == CALLBACK_IMAGE_UPGRADE_DONE)
async def on_image_upgrade_done(callback: CallbackQuery) -> None:
    # The "✅ Готово" button left behind after a successful upgrade is
    # inert by design (see design doc) — this only stops the client-side
    # loading spinner if someone taps it anyway.
    await _safe_answer(callback)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_handlers_refine.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/refine.py tests/test_handlers_refine.py
git commit -m "feat: implement realistic-photo upgrade handler"
```

---

### Task 6: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`
Expected: all tests pass (389 pre-existing + the ones added in Tasks 1, 3, 4, 5 in this plan), no warnings turned errors, no skips introduced.

- [ ] **Step 2: Manual read-through of the two modified send_photo call sites**

Open `bot/handlers/refine.py` and `bot/handlers/start.py`, confirm both `on_refine_image` and `on_photo_gen_description` pass `reply_markup=build_image_upgrade_keyboard(language)` and both store `last_image_prompt` in state before calling `ai_gateway.generate_image`. This is the one behavior a passing test suite can't fully rule out breaking silently (e.g. an accidental second `reply_markup=` kwarg or a typo'd key name that both the handler and its test happen to share).

- [ ] **Step 3: Confirm no stray references to the old two-argument `generate_image` call remain unintentionally changed**

Run: `grep -n "generate_image(" bot/handlers/refine.py bot/handlers/start.py`
Expected: three call sites — `on_refine_image` and `on_photo_gen_description` still call `ai_gateway.generate_image(image_prompt)` with no `model=` (cheap default preserved), and `on_image_upgrade` calls it with `model=settings.ai_gateway_premium_image_model`.

This task has no commit of its own — it's a gate before considering the plan done. If Step 1 fails, return to the task that introduced the failure; do not patch tests to hide a real regression.
