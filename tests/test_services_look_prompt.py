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
