from __future__ import annotations

import httpx
import pytest
import respx

from bot.services import digest
from bot.services.ai_gateway import AIGatewayTimeoutError

NEWS_URL = "https://news.google.com/rss/search"
PAPERS_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Google News</title>
<item>
<title>Новость про психологию №1</title>
<link>https://news.example.com/article-1</link>
<pubDate>Tue, 28 Jul 2026 08:00:00 GMT</pubDate>
</item>
<item>
<title>Новость про психологию №2</title>
<link>https://news.example.com/article-2</link>
<pubDate>Tue, 28 Jul 2026 07:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""


def _papers_payload(items: list[dict]) -> dict:
    return {"total": len(items), "offset": 0, "data": items}


# --- fetch_viral_news ---


@respx.mock
@pytest.mark.asyncio
async def test_fetch_viral_news_parses_rss_entries():
    respx.get(NEWS_URL).mock(
        return_value=httpx.Response(200, content=RSS_SAMPLE.encode("utf-8"))
    )

    items = await digest.fetch_viral_news("психология")

    assert items == [
        digest.DigestItem(title="Новость про психологию №1", url="https://news.example.com/article-1"),
        digest.DigestItem(title="Новость про психологию №2", url="https://news.example.com/article-2"),
    ]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_viral_news_caps_at_four_items():
    many_items = "".join(
        f"<item><title>Новость {i}</title><link>https://news.example.com/{i}</link></item>"
        for i in range(10)
    )
    rss = f"<?xml version=\"1.0\"?><rss version=\"2.0\"><channel>{many_items}</channel></rss>"
    respx.get(NEWS_URL).mock(return_value=httpx.Response(200, content=rss.encode("utf-8")))

    items = await digest.fetch_viral_news("тема")

    assert len(items) == 4


@respx.mock
@pytest.mark.asyncio
async def test_fetch_viral_news_returns_empty_list_for_empty_feed():
    empty_rss = "<?xml version=\"1.0\"?><rss version=\"2.0\"><channel></channel></rss>"
    respx.get(NEWS_URL).mock(return_value=httpx.Response(200, content=empty_rss.encode("utf-8")))

    items = await digest.fetch_viral_news("тема")

    assert items == []


@respx.mock
@pytest.mark.asyncio
async def test_fetch_viral_news_raises_on_http_error():
    respx.get(NEWS_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(httpx.HTTPStatusError):
        await digest.fetch_viral_news("тема")


# --- fetch_scientific_papers ---


@respx.mock
@pytest.mark.asyncio
async def test_fetch_scientific_papers_prefers_recent_sorted_by_citations():
    respx.get(PAPERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=_papers_payload(
                [
                    {"title": "Новый метод КПТ", "url": "https://s2.test/abc", "year": 2026, "citationCount": 5},
                    {"title": "Ещё одна статья 2026", "url": "https://s2.test/ghi", "year": 2026, "citationCount": 50},
                    {"title": "Старое исследование", "url": "https://s2.test/def", "year": 2020, "citationCount": 500},
                ]
            ),
        )
    )

    items = await digest.fetch_scientific_papers("психология")

    assert items == [
        digest.DigestItem(title="Ещё одна статья 2026", url="https://s2.test/ghi"),
        digest.DigestItem(title="Новый метод КПТ", url="https://s2.test/abc"),
    ]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_scientific_papers_falls_back_to_all_when_none_recent():
    respx.get(PAPERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=_papers_payload(
                [{"title": "Старое исследование", "url": "https://s2.test/def", "year": 2020, "citationCount": 500}]
            ),
        )
    )

    items = await digest.fetch_scientific_papers("тема")

    assert items == [digest.DigestItem(title="Старое исследование", url="https://s2.test/def")]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_scientific_papers_caps_at_three_items():
    payload = _papers_payload(
        [
            {"title": f"Статья {i}", "url": f"https://s2.test/{i}", "year": 2026, "citationCount": i}
            for i in range(10)
        ]
    )
    respx.get(PAPERS_URL).mock(return_value=httpx.Response(200, json=payload))

    items = await digest.fetch_scientific_papers("тема")

    assert len(items) == 3


@respx.mock
@pytest.mark.asyncio
async def test_fetch_scientific_papers_returns_empty_list_for_no_results():
    respx.get(PAPERS_URL).mock(return_value=httpx.Response(200, json=_papers_payload([])))

    items = await digest.fetch_scientific_papers("тема")

    assert items == []


# --- synthesize_new_methods ---


@pytest.mark.asyncio
async def test_synthesize_new_methods_returns_none_when_both_sources_empty():
    result = await digest.synthesize_new_methods([], [], "тема")

    assert result is None


@pytest.mark.asyncio
async def test_synthesize_new_methods_returns_none_when_ai_says_no(monkeypatch):
    from bot.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "generate_text", __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value="нет"))
    news = [digest.DigestItem(title="Новость", url="https://news.example.com/1")]

    result = await digest.synthesize_new_methods(news, [], "тема")

    assert result is None


@pytest.mark.asyncio
async def test_synthesize_new_methods_returns_ai_summary(monkeypatch):
    from unittest.mock import AsyncMock

    from bot.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "generate_text", AsyncMock(return_value="Используется новый формат коротких сессий."))
    news = [digest.DigestItem(title="Новость", url="https://news.example.com/1")]

    result = await digest.synthesize_new_methods(news, [], "тема")

    assert result == "Используется новый формат коротких сессий."


# --- build_digest: per-source failure isolation ---


@respx.mock
@pytest.mark.asyncio
async def test_build_digest_survives_news_source_failure(monkeypatch):
    from unittest.mock import AsyncMock

    from bot.services import ai_gateway

    respx.get(NEWS_URL).mock(return_value=httpx.Response(500))
    respx.get(PAPERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=_papers_payload(
                [{"title": "Статья", "url": "https://s2.test/1", "year": 2026, "citationCount": 1}]
            ),
        )
    )
    monkeypatch.setattr(ai_gateway, "generate_text", AsyncMock(return_value="нет"))

    result = await digest.build_digest("тема")

    assert result.news == []
    assert len(result.papers) == 1


@respx.mock
@pytest.mark.asyncio
async def test_build_digest_survives_ai_synthesis_failure(monkeypatch):
    from unittest.mock import AsyncMock

    from bot.services import ai_gateway

    respx.get(NEWS_URL).mock(return_value=httpx.Response(200, content=RSS_SAMPLE.encode("utf-8")))
    respx.get(PAPERS_URL).mock(return_value=httpx.Response(200, json=_papers_payload([])))
    monkeypatch.setattr(ai_gateway, "generate_text", AsyncMock(side_effect=AIGatewayTimeoutError("timed out")))

    result = await digest.build_digest("тема")

    assert len(result.news) == 2
    assert result.methods_summary is None


@respx.mock
@pytest.mark.asyncio
async def test_build_digest_all_sources_empty(monkeypatch):
    from unittest.mock import AsyncMock

    from bot.services import ai_gateway

    empty_rss = "<?xml version=\"1.0\"?><rss version=\"2.0\"><channel></channel></rss>"
    respx.get(NEWS_URL).mock(return_value=httpx.Response(200, content=empty_rss.encode("utf-8")))
    respx.get(PAPERS_URL).mock(return_value=httpx.Response(200, json=_papers_payload([])))
    mock_generate = AsyncMock()
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    result = await digest.build_digest("тема")

    assert result.news == []
    assert result.papers == []
    assert result.methods_summary is None
    mock_generate.assert_not_awaited()


# --- format_digest_message ---


def test_format_digest_message_includes_all_non_empty_sections():
    result = digest.DigestResult(
        topic="психология",
        news=[digest.DigestItem(title="Новость", url="https://news.example.com/1")],
        papers=[digest.DigestItem(title="Статья", url="https://s2.test/1")],
        methods_summary="Новый формат коротких сессий.",
    )

    text = digest.format_digest_message(result, "ru")

    assert "психология" in text
    assert "Новость" in text and "https://news.example.com/1" in text
    assert "Статья" in text and "https://s2.test/1" in text
    assert "Новый формат коротких сессий." in text


def test_format_digest_message_omits_empty_sections():
    result = digest.DigestResult(topic="тема", news=[], papers=[], methods_summary="Только методики.")

    text = digest.format_digest_message(result, "ru")

    from bot.locales.loader import get_string

    assert get_string("digest_section_news", "ru") not in text
    assert get_string("digest_section_papers", "ru") not in text
    assert "Только методики." in text


def test_format_digest_message_returns_empty_result_text_when_nothing_found():
    result = digest.DigestResult(topic="тема", news=[], papers=[], methods_summary=None)

    text = digest.format_digest_message(result, "ru")

    from bot.locales.loader import get_string

    assert text == get_string("digest_empty_result", "ru", topic="тема")


def test_format_digest_message_truncates_to_telegram_limit():
    # Simulates real Google News RSS redirect URLs, which are long (400-900+
    # chars each) — 4 news + 3 papers with such URLs can push the unbounded
    # assembled message past Telegram's 4096-char send_message/answer limit.
    long_url = "https://news.google.com/rss/articles/" + ("A" * 800)
    result = digest.DigestResult(
        topic="психология",
        news=[digest.DigestItem(title=f"Новость {i}", url=long_url) for i in range(4)],
        papers=[digest.DigestItem(title=f"Статья {i}", url=long_url) for i in range(3)],
        methods_summary="Используется новый формат коротких сессий.",
    )

    text = digest.format_digest_message(result, "ru")

    assert len(text) <= 4096
