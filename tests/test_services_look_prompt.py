from __future__ import annotations

import pytest

from bot.services.look_prompt import BANNED_PHRASES, build_look_prompt, mentions_hair


def test_prompt_carries_the_user_description():
    prompt = build_look_prompt("белая рубашка, тёмный фон, мягкий свет")

    assert "белая рубашка, тёмный фон, мягкий свет" in prompt


def test_prompt_demands_a_close_up_head_and_shoulders_frame():
    # Первый образ был собран общим планом, лицо заняло пятую часть кадра,
    # и движок был забракован несправедливо. Крупный план — не пожелание.
    prompt = build_look_prompt("студия").lower()

    assert "close-up" in prompt
    assert "head and shoulders" in prompt


def test_prompt_demands_a_frontal_pose_and_the_same_face():
    prompt = build_look_prompt("студия").lower()

    assert "frontal" in prompt
    assert "same face" in prompt


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_banned_phrases_are_stripped_from_the_description(phrase):
    # «editorial fashion photography» и родня тянут к обобщённому модельному
    # лицу — проверено на живых генерациях.
    prompt = build_look_prompt(f"студия, {phrase}, мягкий свет")

    assert phrase not in prompt.lower()


def test_empty_description_still_produces_a_usable_prompt():
    prompt = build_look_prompt("   ")

    assert prompt.strip()
    assert "close-up" in prompt.lower()


@pytest.mark.parametrize(
    "description",
    ["сделай каре", "длинные волосы", "hair down", "другая причёска", "ПРИЧЕСКА выше"],
)
def test_hair_changes_are_detected(description):
    assert mentions_hair(description) is True


@pytest.mark.parametrize("description", ["белая рубашка", "тёмный фон", "мягкий свет"])
def test_plain_wardrobe_descriptions_are_not_hair(description):
    assert mentions_hair(description) is False


def test_banned_phrase_removal_leaves_clean_punctuation_between_fragments():
    # Вырезание фразы из середины строки не должно оставлять ",," или двойной
    # пробел — соседние фрагменты должны остаться читаемыми.
    prompt = build_look_prompt("студия, beauty retouch, мягкий свет")

    assert ",," not in prompt
    assert "  " not in prompt
    assert "студия" in prompt
    assert "мягкий свет" in prompt


def test_banned_phrase_removal_does_not_mangle_longer_words():
    # "beauty retouch" не должен вырезаться из середины "retouching".
    prompt = build_look_prompt("no beauty retouching please")

    assert "retouching" in prompt


def test_mentions_hair_does_not_match_furniture_words():
    assert mentions_hair("leather chair in the background") is False
    assert mentions_hair("кресло у стены") is False


def test_mentions_hair_still_matches_real_hair_words():
    assert mentions_hair("haircut") is True
    assert mentions_hair("волосы убраны") is True
