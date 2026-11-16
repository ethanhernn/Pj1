"""Unit tests for ntfy push header handling.

The live cron crashed when a filing title containing an em dash was placed in
the ntfy Title header: Python's http.client encodes header values as latin-1,
which can't represent U+2014. These tests pin the encode-and-survive behavior.
"""

from __future__ import annotations

from email.header import decode_header, make_header

import pytest

from src import notify


class _FakeResponse:
    status_code = 200
    text = "ok"


@pytest.fixture
def captured(monkeypatch):
    """Capture the headers/data handed to requests.post without hitting the network."""
    calls: list[dict] = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append({"url": url, "data": data, "headers": headers})
        return _FakeResponse()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    return calls


def _assert_latin1_safe(headers: dict) -> None:
    """Every header value must be encodable as latin-1 or http.client would raise."""
    for value in headers.values():
        value.encode("latin-1")


def test_ascii_title_passes_through_unchanged(captured):
    assert notify.push("https://ntfy.sh", "topic", "body", title="Plain ASCII Title")
    headers = captured[0]["headers"]
    assert headers["Title"] == "Plain ASCII Title"
    _assert_latin1_safe(headers)


def test_em_dash_title_does_not_crash_and_round_trips(captured):
    title = "New 13F — Situational Awareness LP"
    assert notify.push("https://ntfy.sh", "topic", "body", title=title)
    headers = captured[0]["headers"]
    # Must be safe to put on the wire...
    _assert_latin1_safe(headers)
    # ...and an RFC 2047-aware reader (like ntfy) recovers the original text.
    assert str(make_header(decode_header(headers["Title"]))) == title


def test_unicode_tags_are_encoded(captured):
    assert notify.push("https://ntfy.sh", "topic", "body", tags=["🚨", "alert"])
    headers = captured[0]["headers"]
    _assert_latin1_safe(headers)
    assert str(make_header(decode_header(headers["Tags"]))) == "🚨,alert"


def test_body_is_sent_as_utf8_bytes(captured):
    notify.push("https://ntfy.sh", "topic", "résumé — go")
    assert captured[0]["data"] == "résumé — go".encode("utf-8")
