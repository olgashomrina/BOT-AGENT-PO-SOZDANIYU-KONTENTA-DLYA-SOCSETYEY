from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx

from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services import ai_gateway
from bot.services.ai_gateway import AIGatewayError

logger = logging.getLogger(LOGGER_NAME)

_HTTP_TIMEOUT_SECONDS = 15.0
_NEWS_RSS_URL = "https://news.google.com/rss/search"
_SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_MAX_NEWS_ITEMS = 4
_MAX_PAPER_ITEMS = 3

# Telegram's hard limit for plain send_message/answer text (Bot API "text"
# field). Google News RSS <link> values are long redirect URLs (400-900+
# chars each); 4 news + 3 papers can push the assembled message past this
# limit, which would make the send fail outright.
_TELEGRAM_MESSAGE_LIMIT = 4096

_METHODS_PROMPT_TEMPLATE = (
    "Вот список свежих новостей и научных статей по теме «{topic}»:\n\n"
    "Новости:\n{news_lines}\n\n"
    "Статьи:\n{paper_lines}\n\n"
    "На основе этого списка кратко (1-2 предложения) опиши на русском "
    "языке, какая новая методика, приём или подход упоминается. Если "
    "ничего похожего на новую методику не видно, ответь одним словом: "
    "\"нет\"."
)

_NO_METHODS_ANSWERS = {"нет", "нет.", "нет данных", "no", "no."}


@dataclass
class DigestItem:
    title: str
    url: str


@dataclass
class DigestResult:
    topic: str
    news: list[DigestItem]
    papers: list[DigestItem]
    methods_summary: str | None


async def fetch_viral_news(topic: str) -> list[DigestItem]:
    params = {"q": topic, "hl": "ru", "gl": "RU", "ceid": "RU:ru"}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(_NEWS_RSS_URL, params=params)
        response.raise_for_status()

    parsed = feedparser.parse(response.content)
    items: list[DigestItem] = []
    for entry in parsed.entries[:_MAX_NEWS_ITEMS]:
        title = getattr(entry, "title", None)
        link = getattr(entry, "link", None)
        if title and link:
            items.append(DigestItem(title=title, url=link))
    return items


async def fetch_scientific_papers(topic: str) -> list[DigestItem]:
    params = {"query": topic, "fields": "title,url,citationCount,year", "limit": 20}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(_SEMANTIC_SCHOLAR_URL, params=params)
        response.raise_for_status()

    payload = response.json()
    papers = payload.get("data") or []

    current_year = datetime.now(timezone.utc).year
    recent = [p for p in papers if isinstance(p.get("year"), int) and p["year"] >= current_year - 1]
    candidates = recent if recent else papers
    candidates = sorted(candidates, key=lambda p: p.get("citationCount") or 0, reverse=True)

    items: list[DigestItem] = []
    for paper in candidates[:_MAX_PAPER_ITEMS]:
        title = paper.get("title")
        url = paper.get("url")
        if title and url:
            items.append(DigestItem(title=title, url=url))
    return items


def _format_items_for_prompt(items: list[DigestItem]) -> str:
    if not items:
        return "(пусто)"
    return "\n".join(f"- {item.title}" for item in items)


async def synthesize_new_methods(
    news: list[DigestItem], papers: list[DigestItem], topic: str
) -> str | None:
    if not news and not papers:
        return None

    prompt = _METHODS_PROMPT_TEMPLATE.format(
        topic=topic,
        news_lines=_format_items_for_prompt(news),
        paper_lines=_format_items_for_prompt(papers),
    )
    summary = await ai_gateway.generate_text(prompt)
    if summary.strip().lower().rstrip(".") in _NO_METHODS_ANSWERS:
        return None
    return summary


async def build_digest(topic: str) -> DigestResult:
    news_result, papers_result = await asyncio.gather(
        fetch_viral_news(topic), fetch_scientific_papers(topic), return_exceptions=True
    )

    if isinstance(news_result, BaseException):
        logger.warning(
            "Digest news source failed",
            extra={"operation": "digest_news", "error_class": type(news_result).__name__},
        )
        news: list[DigestItem] = []
    else:
        news = news_result

    if isinstance(papers_result, BaseException):
        logger.warning(
            "Digest papers source failed",
            extra={"operation": "digest_papers", "error_class": type(papers_result).__name__},
        )
        papers: list[DigestItem] = []
    else:
        papers = papers_result

    try:
        methods_summary = await synthesize_new_methods(news, papers, topic)
    except AIGatewayError as exc:
        logger.warning(
            "Digest methods synthesis failed",
            extra={"operation": "digest_methods", "error_class": type(exc).__name__},
        )
        methods_summary = None

    return DigestResult(topic=topic, news=news, papers=papers, methods_summary=methods_summary)


def _format_item_lines(items: list[DigestItem]) -> str:
    return "\n".join(f"{index}. {item.title} — {item.url}" for index, item in enumerate(items, start=1))


def format_digest_message(result: DigestResult, language: str) -> str:
    if not result.news and not result.papers and not result.methods_summary:
        return get_string("digest_empty_result", language, topic=result.topic)

    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    parts = [get_string("digest_title", language, topic=result.topic, date=today)]

    if result.news:
        parts.append(
            f"{get_string('digest_section_news', language)}\n{_format_item_lines(result.news)}"
        )
    if result.papers:
        parts.append(
            f"{get_string('digest_section_papers', language)}\n{_format_item_lines(result.papers)}"
        )
    if result.methods_summary:
        parts.append(f"{get_string('digest_section_methods', language)}\n{result.methods_summary}")

    message = "\n\n".join(parts)
    if len(message) > _TELEGRAM_MESSAGE_LIMIT:
        message = message[: _TELEGRAM_MESSAGE_LIMIT - 1] + "…"
    return message


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
