from __future__ import annotations

import pytest

from bot.services.input_processor import LinkExtractionError, extract_from_link


def test_extract_from_link_success(monkeypatch):
    monkeypatch.setattr(
        "trafilatura.fetch_url", lambda url, **kwargs: "<html>irrelevant</html>"
    )
    monkeypatch.setattr(
        "trafilatura.extract", lambda downloaded, **kwargs: "Извлечённый текст статьи."
    )

    result = extract_from_link("https://example.com/article")

    assert result == "Извлечённый текст статьи."


def test_extract_from_link_raises_when_fetch_returns_none(monkeypatch):
    monkeypatch.setattr("trafilatura.fetch_url", lambda url, **kwargs: None)

    with pytest.raises(LinkExtractionError):
        extract_from_link("https://example.com/unreachable")


def test_extract_from_link_raises_when_extract_returns_none(monkeypatch):
    monkeypatch.setattr("trafilatura.fetch_url", lambda url, **kwargs: "<html></html>")
    monkeypatch.setattr("trafilatura.extract", lambda downloaded, **kwargs: None)

    with pytest.raises(LinkExtractionError):
        extract_from_link("https://example.com/empty")


def test_extract_from_link_raises_when_extract_returns_blank(monkeypatch):
    monkeypatch.setattr("trafilatura.fetch_url", lambda url, **kwargs: "<html></html>")
    monkeypatch.setattr("trafilatura.extract", lambda downloaded, **kwargs: "   ")

    with pytest.raises(LinkExtractionError):
        extract_from_link("https://example.com/blank")


def test_extract_from_link_raises_when_fetch_raises_network_error(monkeypatch):
    def _raise(url, **kwargs):
        raise OSError("network unreachable")

    monkeypatch.setattr("trafilatura.fetch_url", _raise)

    with pytest.raises(LinkExtractionError):
        extract_from_link("https://example.com/down")
