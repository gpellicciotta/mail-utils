"""Shared raw-MIME-header decoding, used by every source parser (`outlook/`, `thunderbird/`) that
reads header text straight off a legacy `email.parser`/`mailbox` API under the classic compat32
policy - which neither unfolds RFC 5322 header folding nor decodes RFC 2047 encoded-words on its own,
unlike the modern `email.policy.default` used elsewhere in this codebase (e.g. `import-eml`,
`store-in-gmail`'s EML reading)."""

import email.errors
import email.header
import re


def decode_header_str(val: str | None) -> str:
    """Decode an RFC 2047 MIME encoded-word header into a clean Python string."""
    if not val:
        return ""
    # A header pulled from a legacy compat32 parse can carry two artifacts that a modern-policy parse
    # would have already resolved: literal RFC 5322 header folding (a raw CRLF followed by whitespace,
    # used to wrap a long header - e.g. a long recipient list - across several physical lines), and an
    # un-decoded RFC 2047 encoded-word (found in real Outlook PST transport headers: `outlook/
    # messages.py::_parse_transport_headers` uses `email.parser.Parser()`, which is compat32 by
    # default and returns encoded-words like "=?iso-8859-1?Q?Kevin_Crabb=E9?=" completely raw). Left
    # unfolded, a raw newline crashes `export --format eml` when it tries to serialize the value into a
    # real header; left un-decoded, the encoded-word never becomes readable text at all - found via
    # T0020's round-trip comparison against real Outlook and Thunderbird archive data.
    val = val.replace("\r\n", "").replace("\n", "").replace("\r", "")
    try:
        parts = email.header.decode_header(val)
        res = []
        for part, enc in parts:
            if isinstance(part, bytes):
                try:
                    res.append(part.decode(enc or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    res.append(part.decode("utf-8", errors="replace"))
            else:
                res.append(str(part))
        return "".join(res)
    except (ValueError, LookupError, UnicodeError, email.errors.HeaderParseError):
        return str(val)


_UNQUOTED_AT_DISPLAY_NAME_RE = re.compile(r'(?P<name>[^,"<>]*@[^,"<>]*?)\s*<(?P<addr>[^<>]*)>')


def quote_unquoted_at_display_names(value: str | None) -> str | None:
    """Quote a display name that contains an unquoted "@" - e.g. a real Thunderbird-sourced sender
    "Panel @ InSites  <info@insitespanel.com>" - before it's used as an RFC 5322 address-list value.

    RFC 5322 requires a display name containing a special character like "@" to be quoted. Left
    unquoted, `email.utils.getaddresses()` (used by every `parse_addresses()` in this codebase) fails
    to parse it too - it either drops the address half entirely or (for the common "same address used
    as its own bogus display name" pattern, e.g. "x@y.com  <x@y.com>") returns nothing at all - so
    `message_addresses` silently loses the row at capture time, long before any export/re-import is
    involved. Applying this at capture time (not just before writing an .eml header) fixes that root
    cause instead of just working around it - found via T0020's round-trip comparison against real
    Thunderbird and Outlook archive data, where dozens of `message_addresses` rows for otherwise
    perfectly normal recipients were missing because of this.

    Only touches a "name <addr>" segment whose name contains an "@" and isn't already quoted; every
    other already-valid segment (a bare address, a properly quoted name, a legacy trailing
    "(comment)") is left untouched."""
    if not value:
        return value
    return _UNQUOTED_AT_DISPLAY_NAME_RE.sub(lambda m: f'"{m.group("name").strip()}" <{m.group("addr")}>', value)


_UNQUOTED_PAREN_DISPLAY_NAME_RE = re.compile(r'(?P<name>[^,"<>]*\([^,"<>]*\)[^,"<>]*?)\s*<(?P<addr>[^<>]*)>')


def quote_unquoted_paren_display_names(value: str | None) -> str | None:
    """Quote a display name that contains unquoted "(" / ")" - e.g. a real Exchange-resolved sender
    "BQTH (Børge Thygesen) <bqth@nnit.com>" - before it's used as an RFC 5322 address-list value.

    RFC 5322 always treats an unquoted "(...)" as a CFWS comment, not literal display-name text - left
    unquoted, `email.policy.default`'s address parsing (used by `import-eml`'s `getaddresses()` call on
    the way back in) mangles the name once it's round-tripped through a real header: sometimes the
    comment's content survives but its parens are dropped ("BQTH (Børge Thygesen)" -> "BQTH Børge
    Thygesen" - not itself data loss, just reformatted), but sometimes the whole comment is discarded
    outright ("COHEN Arieh (EXT)" -> "COHEN Arieh" - genuinely losing the "(EXT)" text) - found via
    T0020's full-scale round-trip comparison, where this was the largest genuine (non-cosmetic) address
    fidelity bug after the unquoted-"," and unquoted-"@" cases above were already fixed. Quoting the
    whole name preserves the parens (and their content) as literal text either way, matching how a
    quoted-string's contents are never treated as CFWS by RFC 5322.

    Only touches a "name <addr>" segment whose name contains "(...)" and isn't already quoted; a
    genuinely trailing legacy comment with no preceding "<addr>" (e.g. a bare
    "tim.vanholder@anubex.com (Cron Daemon)") is a different, already-handled shape (see
    `_strip_trailing_comments` in `scripts/local-roundtrip-test.py`) and is left untouched here."""
    if not value:
        return value
    return _UNQUOTED_PAREN_DISPLAY_NAME_RE.sub(lambda m: f'"{m.group("name").strip()}" <{m.group("addr")}>', value)


_UNQUOTED_BRACKET_DISPLAY_NAME_RE = re.compile(r'(?P<name>[^,"<>]*\[[^,"<>]*\][^,"<>]*?)\s*<(?P<addr>[^<>]*)>')


def quote_unquoted_bracket_display_names(value: str | None) -> str | None:
    """Quote a display name that contains unquoted "[" / "]" - e.g. a real personal-address-book
    annotation "Els Van Peer [gmail] <vanpeer.els@gmail.com>" or "Johan Van De Velde [prive]
    <Johan_vdvelde@telenet.be>" - before it's used as an RFC 5322 address-list value.

    Same failure mode as the unquoted-"(...)" case (`quote_unquoted_paren_display_names`): RFC 5322
    never gives "[...]" any special meaning inside a display name, but left unquoted,
    `email.utils.getaddresses()` (used by every `parse_addresses()` in this codebase, including
    `import-eml`'s reimport) doesn't just reformat it - it drops the address half entirely, e.g.
    "Els Van Peer [gmail] <vanpeer.els@gmail.com>" reimports as bare `"Els Van Peer"` with the real
    address gone - a genuine, confirmed `message_addresses` row loss, not cosmetic reformatting -
    found via T0020's full-scale round-trip comparison (2 real messages, both real personal contacts
    with an inline "[gmail]"/"[prive]" annotation in their captured display name).

    Only touches a "name <addr>" segment whose name contains "[...]" and isn't already quoted; a name
    already handled by `quote_unquoted_paren_display_names` (i.e. one that also contains "(...)") is
    unaffected here since that pass already wraps the whole name - including any "[...]" inside it -
    in quotes first."""
    if not value:
        return value
    return _UNQUOTED_BRACKET_DISPLAY_NAME_RE.sub(lambda m: f'"{m.group("name").strip()}" <{m.group("addr")}>', value)


_COMMA_RECIPIENT_RE = re.compile(r"^(?P<name>[^<>]*)<(?P<addr>[^<>]*)>$")
_ALREADY_QUOTED_PREFIX_RE = re.compile(r'^(?:"[^"]*"\s*,\s*)+$')
_BARE_QUOTED_LABEL_RE = re.compile(r'^"[^"]*"$')


def _split_top_level_commas(value: str) -> list[str]:
    """Split on "," outside of any `"..."` quoted segment, keeping each piece's own text (including
    the comma-adjacent whitespace) intact - so re-joining every returned piece with "," always
    reproduces `value` exactly."""
    tokens = []
    buf = []
    in_quotes = False
    for ch in value:
        if ch == '"':
            in_quotes = not in_quotes
            buf.append(ch)
        elif ch == "," and not in_quotes:
            tokens.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    tokens.append("".join(buf))
    return tokens


def quote_unquoted_comma_display_names(value: str | None) -> str | None:
    """Quote a display name that contains an unquoted "," - e.g. a real Outlook/Exchange-resolved
    recipient "Kumar, Rajesh <rajesh.kumar@astadia.com>" - before it's used as an RFC 5322
    address-list value.

    A comma is RFC 5322's own address-list separator, so `email.utils.getaddresses()` (used by every
    `parse_addresses()` in this codebase) can't tell "Kumar, Rajesh <addr>" (one recipient, "Last,
    First" display name) apart from two genuinely separate list entries - it splits it into a bogus
    address-less "Kumar" row and a "Rajesh <addr>" row that's lost half its real display name. Real
    corporate Exchange directories commonly resolve recipients into exactly this unquoted "Last,
    First" form - found via T0020's full-scale round-trip comparison, where this pattern accounted for
    the large majority of the 6806 reported problems.

    Unlike the unquoted-"@" case (`quote_unquoted_at_display_names`), a plain regex substitution isn't
    viable here, since a comma is *usually* a real separator - "alice@x.com, Kumar, Rajesh <addr>"
    must stay 2 recipients, not collapse into 1. Instead, walks the whole comma-separated value left to
    right, only treating a comma as "part of the previous display name" when the text accumulated so
    far doesn't yet look like a complete recipient (no `<...>` address and no bare "@") - once it does,
    that's a real separator and accumulation starts over for the next recipient. Already-quoted
    segments (a comma inside `"..."`) are never touched, since `getaddresses()` already parses those
    correctly.

    One shape needs distinguishing from the "Kumar, Rajesh" case: a bare, already-quoted, address-less
    label - e.g. a real '"Banca March CC", Taix Ramonell, Ramón José <rtaix@bancamarch.es>, "Segura
    Ginard, Juan Carlos" <jsegura@bancamarch.es>' (a distribution-list-style tag some corporate senders
    prepend to a Cc list - common enough in older Exchange/Lotus-sourced mail to be worth handling, not
    a garbled one-off - immediately followed by the *real*, separately unquoted "Last, First" name of
    the list's own first recipient). Since the label has no `<addr>` of its own, the plain
    accumulate-until-`<...>`-appears loop below would otherwise pull it *and* that following name into
    one group, merging and re-quoting the whole thing into an invalid doubly-quoted mess:
    '""Banca March CC", Taix Ramonell, Ramón José"' <rtaix@...> - losing the fact that these were two
    separate list entries, not one three-part name (found via T0020's full-scale round-trip
    comparison). A token that is *itself* already a complete, standalone `"..."` quoted string (no
    address markers) is therefore peeled off into its own single-token group the moment it's seen with
    nothing else pending - it never gets a chance to accumulate with what follows. `_ALREADY_QUOTED_PREFIX_RE`
    is a second, output-stage safety net for the same shape in case something *was* already pending
    when the label appeared (e.g. a preceding unquoted fragment) - the grouping fix above prevents the
    common case, this catches the residual one instead of re-quoting it."""
    if not value or "," not in value:
        return value
    tokens = _split_top_level_commas(value)
    groups: list[list[str]] = []
    pending: list[str] = []
    for tok in tokens:
        if not pending and _BARE_QUOTED_LABEL_RE.match(tok.strip()):
            groups.append([tok])
            continue
        pending.append(tok)
        joined = ",".join(pending)
        if ("<" in joined and ">" in joined) or "@" in joined:
            groups.append(pending)
            pending = []
    if pending:
        groups.append(pending)

    out_parts = []
    for group in groups:
        raw = ",".join(group)
        if len(group) > 1:
            m = _COMMA_RECIPIENT_RE.match(raw.strip())
            if m and "," in m.group("name") and not _ALREADY_QUOTED_PREFIX_RE.match(m.group("name")):
                leading_space = " " if raw != raw.lstrip() else ""
                # `name` may already carry a nested `"..."` substring added by an earlier
                # quote_unquoted_paren_display_names/quote_unquoted_at_display_names pass over a
                # comma-containing display name (e.g. "Broeders, M.A.J.L. (Marco)" gets partially
                # quoted to 'Broeders, "M.A.J.L. (Marco)"' before this function ever sees it, since
                # the comma splits it into two segments neither earlier function's own regex can
                # cross). Wrapping that in a second, outer pair of quotes produces invalid doubly-
                # nested quoting - `"Broeders,"M.A.J.L. (Marco)""` - that a real compose/reparse
                # cycle then mangles for real (dropped comment/parens content). Since this function
                # is about to apply the one true, complete quoting for the whole name anyway, any
                # inner quote characters are now redundant and stripped before the final wrap.
                name = m.group("name").strip().replace('"', "")
                out_parts.append(f'{leading_space}"{name}" <{m.group("addr")}>')
                continue
        out_parts.append(raw)
    return ",".join(out_parts)
