from __future__ import annotations

import pytest

from bot.locales import ru
from bot.services import platform_package


def _note_keys(package) -> list[str]:
    return [note.key for note in package.notes]


def test_build_all_packages_covers_the_three_external_platforms_in_order():
    packages = platform_package.build_all_packages("Короткий пост.")

    assert [package.platform for package in packages] == [
        "instagram",
        "youtube_shorts",
        "facebook",
    ]


def test_hashtag_line_is_split_off_the_body():
    text = "Текст поста.\n\n#маркетинг #контент #смм"

    package = platform_package.build_package(text, "facebook")

    assert package.caption == "Текст поста."
    assert package.hashtags == ("#маркетинг", "#контент", "#смм")


def test_a_final_line_that_is_not_all_hashtags_stays_in_the_body():
    # A closing CTA that merely mentions a tag must not be mistaken for the
    # hashtag line and torn off the post.
    text = "Текст поста.\nПишите в #комментариях, что думаете."

    package = platform_package.build_package(text, "facebook")

    assert package.caption.endswith("что думаете.")
    assert package.hashtags == ()


def test_instagram_trims_hashtags_to_its_own_norm_and_says_so():
    tags = " ".join(f"#тег{i}" for i in range(12))
    package = platform_package.build_package(f"Текст.\n\n{tags}", "instagram")

    assert len(package.hashtags) == platform_package.PROFILES["instagram"].hashtag_max
    assert package.hashtags[0] == "#тег0"
    assert "package_note_hashtags_trimmed" in _note_keys(package)


def test_facebook_keeps_hashtags_when_they_are_within_the_norm():
    package = platform_package.build_package("Текст.\n\n#один #два", "facebook")

    assert package.hashtags == ("#один", "#два")
    assert "package_note_hashtags_trimmed" not in _note_keys(package)


def test_links_are_extracted_and_flagged_where_they_are_not_clickable():
    text = "Разбор тут: https://example.com/article — заходите."

    instagram = platform_package.build_package(text, "instagram")
    facebook = platform_package.build_package(text, "facebook")

    assert instagram.links == ("https://example.com/article",)
    assert "package_note_links_not_clickable" in _note_keys(instagram)
    # Same link, clickable platform: extracted for reference, but no warning.
    assert facebook.links == ("https://example.com/article",)
    assert "package_note_links_not_clickable" not in _note_keys(facebook)


def test_no_link_warning_when_the_post_has_no_links():
    package = platform_package.build_package("Текст без ссылок.", "instagram")

    assert package.links == ()
    assert "package_note_links_not_clickable" not in _note_keys(package)


def test_caption_over_the_limit_is_cut_on_a_word_boundary_and_flagged():
    limit = platform_package.PROFILES["instagram"].caption_limit
    long_text = "слово " * (limit // 3)

    package = platform_package.build_package(long_text, "instagram")

    assert len(package.caption) <= limit
    assert package.caption.endswith("…")
    # Word boundary: the cut must not leave a half-word before the ellipsis.
    assert package.caption[:-1].rstrip().endswith("слово")
    assert "package_note_caption_truncated" in _note_keys(package)


def test_hashtags_are_reserved_out_of_the_caption_budget_not_cut_off_by_it():
    # Instagram counts hashtags inside the same 2200-character caption, so a
    # long body must lose characters to make room for the tags rather than the
    # tags being silently dropped after truncation.
    limit = platform_package.PROFILES["instagram"].caption_limit
    tags = "#первый #второй #третий"
    package = platform_package.build_package("слово " * limit + f"\n\n{tags}", "instagram")

    assert package.hashtags == ("#первый", "#второй", "#третий")
    assert len(package.caption) + len(" ".join(package.hashtags)) + 2 <= limit


def test_short_caption_is_left_exactly_as_written():
    package = platform_package.build_package("Совсем короткий пост.", "facebook")

    assert package.caption == "Совсем короткий пост."
    assert "package_note_caption_truncated" not in _note_keys(package)


def test_youtube_shorts_derives_a_title_from_the_first_sentence():
    text = "Почему кружки дают охват. Дальше идёт длинное объяснение причин."

    package = platform_package.build_package(text, "youtube_shorts")

    assert package.title == "Почему кружки дают охват"


def test_youtube_title_is_capped_at_the_platform_limit():
    limit = platform_package.PROFILES["youtube_shorts"].title_limit
    package = platform_package.build_package("слово " * 200, "youtube_shorts")

    assert package.title is not None
    assert len(package.title) <= limit


def test_platforms_without_a_title_field_get_none():
    package = platform_package.build_package("Текст.", "instagram")

    assert package.title is None


def test_youtube_package_always_carries_the_shorts_tag():
    package = platform_package.build_package("Текст.\n\n#контент", "youtube_shorts")

    assert "#Shorts" in package.hashtags


def test_shorts_tag_is_not_duplicated_when_the_post_already_has_it():
    package = platform_package.build_package("Текст.\n\n#Shorts #контент", "youtube_shorts")

    assert package.hashtags.count("#Shorts") == 1


def test_caption_preview_hint_is_given_where_the_caption_is_the_hook():
    package = platform_package.build_package("Текст.", "instagram")

    assert "package_note_preview" in _note_keys(package)


def test_shorts_gets_no_caption_preview_hint_because_the_title_is_the_hook():
    package = platform_package.build_package("Текст.", "youtube_shorts")

    assert "package_note_preview" not in _note_keys(package)


def test_every_platform_reminds_about_ai_disclosure():
    for platform in platform_package.PROFILES:
        package = platform_package.build_package("Текст.", platform)

        assert "package_note_ai_disclosure" in _note_keys(package), platform


def test_media_spec_reports_a_vertical_format_for_every_platform():
    # The Telegram video note is square; nothing here may hand back 1:1, or
    # the user would publish a letterboxed clip.
    for platform, profile in platform_package.PROFILES.items():
        assert profile.video_aspect == "9:16", platform

        package = platform_package.build_package("Текст.", platform)
        assert package.media_spec.params["aspect"] == "9:16"


def test_unknown_platform_is_rejected():
    with pytest.raises(KeyError):
        platform_package.build_package("Текст.", "tiktok")


def test_every_note_and_spec_key_exists_in_the_locales():
    # A note key that has no locale string would surface to the user as a
    # KeyError at send time, not at build time — catch it here instead.
    keys = {platform_package.MEDIA_SPEC_KEY}
    for platform in platform_package.PROFILES:
        text = "Текст со ссылкой https://example.com.\n\n" + " ".join(
            f"#тег{i}" for i in range(20)
        )
        package = platform_package.build_package(text, platform)
        keys.update(note.key for note in package.notes)

    for key in keys:
        assert key in ru.STRINGS, key


def test_package_carries_the_human_readable_platform_name():
    package = platform_package.build_package("Текст.", "instagram")

    assert package.display_name == "Instagram Reels"
