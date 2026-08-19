import pytest

from mail_utils.filters import FilterError, message_matches, parse_filter


def test_parse_filter_splits_bare_words_and_key_value_pairs():
    tokens = parse_filter('label:Work from:jane subject:"quarterly report" hello')
    assert tokens == [
        ("label", "Work"),
        ("from", "jane"),
        ("subject", "quarterly report"),
        ("*", "hello"),
    ]


def test_parse_filter_rejects_unrecognized_keyword():
    with pytest.raises(FilterError):
        parse_filter("is:unread")


def _ctx(**overrides):
    ctx = {
        "labels": ["Work"],
        "addresses": {"from": [("jane@x.com", "Jane Doe")], "to": [("me@x.com", None)]},
        "has_attachment": False,
        "internal_date_ms": 1735689600000,  # 2025-01-01T00:00:00Z
        "subject": "Quarterly report",
        "body_text": "Please find attached the numbers.",
    }
    ctx.update(overrides)
    return ctx


def test_bare_word_matches_subject_or_body():
    assert message_matches(parse_filter("quarterly"), **_ctx())
    assert message_matches(parse_filter("numbers"), **_ctx())
    assert not message_matches(parse_filter("invoice"), **_ctx())


def test_label_match_is_exact_case_insensitive():
    assert message_matches(parse_filter("label:work"), **_ctx())
    assert not message_matches(parse_filter("label:wor"), **_ctx())


def test_from_matches_address_or_name():
    assert message_matches(parse_filter("from:jane"), **_ctx())
    assert message_matches(parse_filter("from:jane@x.com"), **_ctx())
    assert not message_matches(parse_filter("from:bob"), **_ctx())


def test_to_role_does_not_match_from_address():
    assert not message_matches(parse_filter("to:jane"), **_ctx())


def test_after_and_before_bracket_internal_date():
    assert message_matches(parse_filter("after:2024/12/31"), **_ctx())
    assert not message_matches(parse_filter("after:2025/01/02"), **_ctx())
    assert message_matches(parse_filter("before:2025/01/02"), **_ctx())
    assert not message_matches(parse_filter("before:2025/01/01"), **_ctx())


def test_after_before_never_match_missing_internal_date():
    assert not message_matches(parse_filter("after:2000/01/01"), **_ctx(internal_date_ms=None))


def test_invalid_date_raises_filter_error():
    with pytest.raises(FilterError):
        message_matches(parse_filter("after:2025-01-01"), **_ctx())


def test_has_attachment():
    assert not message_matches(parse_filter("has:attachment"), **_ctx())
    assert message_matches(parse_filter("has:attachment"), **_ctx(has_attachment=True))


def test_has_unsupported_value_raises():
    with pytest.raises(FilterError):
        message_matches(parse_filter("has:document"), **_ctx())


def test_multiple_tokens_are_anded():
    tokens = parse_filter("label:Work from:jane quarterly")
    assert message_matches(tokens, **_ctx())
    assert not message_matches(tokens, **_ctx(labels=["Personal"]))
