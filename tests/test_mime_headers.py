from mail_utils.mime_headers import (
    decode_header_str,
    quote_unquoted_at_display_names,
    quote_unquoted_bracket_display_names,
    quote_unquoted_comma_display_names,
    quote_unquoted_paren_display_names,
)


def test_decode_header_str_decodes_and_unfolds():
    assert decode_header_str("Plain Subject") == "Plain Subject"
    assert decode_header_str("=?utf-8?B?Q2Fmw6kgVGVzdA==?=") == "Café Test"
    assert decode_header_str("") == ""
    assert decode_header_str(None) == ""
    assert decode_header_str("A <a@example.com>,\n\tB <b@example.com>") == "A <a@example.com>,\tB <b@example.com>"


def test_quote_unquoted_at_display_names_quotes_only_the_offending_segment():
    assert (
        quote_unquoted_at_display_names("Panel @ InSites  <info@insitespanel.com>") == '"Panel @ InSites" <info@insitespanel.com>'
    )
    assert (
        quote_unquoted_at_display_names("giovanni.pellicciotta@gmail.com  <giovanni.pellicciotta@gmail.com>")
        == '"giovanni.pellicciotta@gmail.com" <giovanni.pellicciotta@gmail.com>'
    )


def test_quote_unquoted_at_display_names_leaves_valid_input_untouched():
    already_quoted = '"Foo @ Bar" <addr@x.com>'
    assert quote_unquoted_at_display_names(already_quoted) == already_quoted

    normal = "Kris Ceuppens <kris.ceuppens@astadia.com>, plain@example.com"
    assert quote_unquoted_at_display_names(normal) == normal

    comment_style = "tim.vanholder@anubex.com (Cron Daemon)"
    assert quote_unquoted_at_display_names(comment_style) == comment_style

    assert quote_unquoted_at_display_names(None) is None
    assert quote_unquoted_at_display_names("") == ""


def test_quote_unquoted_at_display_names_in_a_multi_entry_list():
    value = "A <a@x.com>, Panel @ InSites <info@insitespanel.com>, B <b@x.com>"
    result = quote_unquoted_at_display_names(value)
    from email.utils import getaddresses

    assert getaddresses([result]) == [
        ("A", "a@x.com"),
        ("Panel @ InSites", "info@insitespanel.com"),
        ("B", "b@x.com"),
    ]


def test_quote_unquoted_comma_display_names_single_recipient():
    assert (
        quote_unquoted_comma_display_names("Kumar, Rajesh <rajesh.kumar@astadia.com>")
        == '"Kumar, Rajesh" <rajesh.kumar@astadia.com>'
    )


def test_quote_unquoted_comma_display_names_preceded_by_bare_address():
    from email.utils import getaddresses

    value = "alice@x.com, Kumar, Rajesh <rajesh.kumar@astadia.com>"
    result = quote_unquoted_comma_display_names(value)
    assert getaddresses([result]) == [
        ("", "alice@x.com"),
        ("Kumar, Rajesh", "rajesh.kumar@astadia.com"),
    ]


def test_quote_unquoted_comma_display_names_between_normal_recipients():
    from email.utils import getaddresses

    value = "A <a@x.com>, Kumar, Rajesh <rajesh.kumar@astadia.com>, B <b@x.com>"
    result = quote_unquoted_comma_display_names(value)
    assert getaddresses([result]) == [
        ("A", "a@x.com"),
        ("Kumar, Rajesh", "rajesh.kumar@astadia.com"),
        ("B", "b@x.com"),
    ]


def test_quote_unquoted_comma_display_names_leaves_valid_input_untouched():
    already_quoted = '"Kumar, Rajesh" <rajesh.kumar@astadia.com>, plain@example.com'
    assert quote_unquoted_comma_display_names(already_quoted) == already_quoted

    normal = "Kris Ceuppens <kris.ceuppens@astadia.com>, plain@example.com"
    assert quote_unquoted_comma_display_names(normal) == normal

    bare_address = "plain@example.com"
    assert quote_unquoted_comma_display_names(bare_address) == bare_address

    assert quote_unquoted_comma_display_names(None) is None
    assert quote_unquoted_comma_display_names("") == ""


def test_quote_unquoted_comma_display_names_multiple_comma_names_in_one_list():
    from email.utils import getaddresses

    value = "Hurley, William <william.hurley@astadia.com>, Sweat, Walter <walter.sweat@astadia.com>"
    result = quote_unquoted_comma_display_names(value)
    assert getaddresses([result]) == [
        ("Hurley, William", "william.hurley@astadia.com"),
        ("Sweat, Walter", "walter.sweat@astadia.com"),
    ]


def test_quote_unquoted_bracket_display_names_quotes_only_the_offending_segment():
    """T0020's full-scale round-trip comparison found two real messages with a personal-
    address-book-style "[gmail]"/"[prive]" annotation in the display name - left unquoted, the address
    itself was silently dropped on reimport (a genuine `message_addresses` row loss, not just
    reformatting)."""
    from email.utils import getaddresses

    value = "Els Van Peer [gmail] <vanpeer.els@gmail.com>"
    result = quote_unquoted_bracket_display_names(value)
    assert result == '"Els Van Peer [gmail]" <vanpeer.els@gmail.com>'
    assert getaddresses([result]) == [("Els Van Peer [gmail]", "vanpeer.els@gmail.com")]

    value2 = "Johan Van De Velde [prive] <Johan_vdvelde@telenet.be>"
    result2 = quote_unquoted_bracket_display_names(value2)
    assert getaddresses([result2]) == [("Johan Van De Velde [prive]", "Johan_vdvelde@telenet.be")]


def test_quote_unquoted_bracket_display_names_leaves_valid_input_untouched():
    already_quoted = '"Foo [bar]" <addr@x.com>'
    assert quote_unquoted_bracket_display_names(already_quoted) == already_quoted

    normal = "Kris Ceuppens <kris.ceuppens@astadia.com>, plain@example.com"
    assert quote_unquoted_bracket_display_names(normal) == normal

    assert quote_unquoted_bracket_display_names(None) is None
    assert quote_unquoted_bracket_display_names("") == ""


def test_quote_unquoted_bracket_display_names_in_a_multi_entry_list():
    from email.utils import getaddresses

    value = "A <a@x.com>, Els Van Peer [gmail] <vanpeer.els@gmail.com>, B <b@x.com>"
    result = quote_unquoted_bracket_display_names(value)
    assert getaddresses([result]) == [
        ("A", "a@x.com"),
        ("Els Van Peer [gmail]", "vanpeer.els@gmail.com"),
        ("B", "b@x.com"),
    ]


def test_quote_unquoted_comma_display_names_strips_nested_quotes_from_prior_paren_pass():
    """T0020's full-scale round-trip comparison found real Outlook display names combining an
    unquoted comma with unquoted parens - e.g. "Broeders, M.A.J.L. (Marco)" - where
    quote_unquoted_paren_display_names (run first, see outlook/thunderbird `_quote_display_names`)
    already quotes the paren-bearing fragment before this function ever sees it, since its own regex
    can't cross the comma: 'Broeders, "M.A.J.L. (Marco)" <addr>'. Blindly wrapping that whole name in
    a second, outer pair of quotes produced invalid doubly-nested quoting -
    '"Broeders,"M.A.J.L. (Marco)""' <addr> - which then genuinely lost the "(Marco)" text on a real
    compose/reparse cycle instead of just reformatting it. This must produce one valid, single
    quoted-string with the parenthetical content intact."""
    from email.utils import getaddresses

    value = "Broeders, M.A.J.L. (Marco) <marco.broeders@nn.nl>"
    combined = quote_unquoted_comma_display_names(quote_unquoted_at_display_names(quote_unquoted_paren_display_names(value)))
    assert '""' not in combined
    parsed = getaddresses([combined])
    assert len(parsed) == 1
    name, addr = parsed[0]
    assert addr == "marco.broeders@nn.nl"
    assert "(Marco)" in name
    assert "Broeders" in name and "M.A.J.L." in name


def test_quote_unquoted_comma_display_names_strips_nested_quotes_from_prior_bracket_pass():
    """Same nested-quoting risk as the paren case above, but for a "Last, First [label]" shape -
    quote_unquoted_bracket_display_names would otherwise leave behind an already-quoted fragment
    quote_unquoted_comma_display_names must not doubly-nest."""
    from email.utils import getaddresses

    value = "Van Peer, Els [gmail] <vanpeer.els@gmail.com>"
    combined = quote_unquoted_comma_display_names(quote_unquoted_at_display_names(quote_unquoted_bracket_display_names(value)))
    assert '""' not in combined
    parsed = getaddresses([combined])
    assert len(parsed) == 1
    name, addr = parsed[0]
    assert addr == "vanpeer.els@gmail.com"
    assert "[gmail]" in name
    assert "Van Peer" in name and "Els" in name
