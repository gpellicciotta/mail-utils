# Project Requirements

This document outlines the high-level vision, functional requirements, technical constraints, and quality standards for `mail-utils`.

## High-Level Vision & Objectives

`mail-utils` is a lightweight, privacy-focused email indexing and archive utility designed to consolidate, search, and export personal email from disparate email providers and local archive formats into a unified local SQLite database. It is read-only by default, with one explicit, opt-in exception (`store-in-gmail`) for writing mail back into Gmail.

## Core Principles
- **Read-Only / Non-Destructive by default**: No command modifies or deletes emails on remote mail servers or within local archive files. The one deliberate exception is `store-in-gmail`, which writes mail (from a prior export or directly from the local database) into a live Gmail mailbox; it never modifies or deletes anything that was already there, and every other command's behavior is unaffected.
- **Local Execution**: All indexes, databases, and full-text searches remain strictly on the local machine
- **Zero Heavy External Dependencies**: Core file format parsers (such as Microsoft Outlook PST and Mozilla Thunderbird PCV/Mbox) are implemented with pure Python standard libraries without native C/C++ library dependencies.
- **Unified Querying & Storage**: Ingested messages from diverse providers (Gmail, Outlook, Thunderbird) are normalized into a single database schema with source prefix isolation (`gmail:`, `outlook:`, `thunderbird:`).

## Functional Requirements

1. Support importing messages from: Gmail, Outlook PST files, Thunderbird PCV files
2. Support exporting messages as Markdown or standard .eml files into hierarchical date-bucketed directories (`<output_dir>/<YYYY>/<MM>/`)
3. Support basic filter operations during import and export
4. Support stats gathering w.r.t.: number of messages, number of labels, number of to/from addresses
5. Support searching imported messages
6. Support storing mail (from an EML export or the local database) back into a live Gmail mailbox, opt-in,
   filterable, resumable, and idempotent

## Technical Requirements & Invariants

1. Third-party dependencies are kept to the minimum actually needed - currently:
   - `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`: required to authenticate
     against and call the Gmail API (`import-gmail`, `store-in-gmail`); no pure-stdlib alternative exists
     for OAuth 2.0 + the Gmail REST API.
   - `PyYAML`: used only for `export --format md`'s YAML frontmatter (`safe_dump`); stdlib has no YAML
     writer. All local archive parsing (Outlook PST, Thunderbird PCV/Mbox) remains zero-dependency, per the
     "Zero Heavy External Dependencies" core principle above.
2. All functionalities are covered by tests
3. Project complies with [cross-project development guidelines](https://github.com/gpellicciotta/dev-guidelines)

