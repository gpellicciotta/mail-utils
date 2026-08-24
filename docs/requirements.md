# Project Requirements

This document outlines the high-level vision, functional requirements, technical constraints, and quality standards for `mail-utils`.

## High-Level Vision & Objectives

`mail-utils` is a lightweight, privacy-focused, read-only email indexing and archive utility designed to consolidate, search, and export personal email from disparate email providers and local archive formats into a unified local SQLite database.

## Core Principles
- **Read-Only / Non-Destructive**: Never modifies or deletes emails on remote mail servers or within local archive files.
- **Local Execution**: All indexes, databases, and full-text searches remain strictly on the local machine
- **Zero Heavy External Dependencies**: Core file format parsers (such as Microsoft Outlook PST and Mozilla Thunderbird PCV/Mbox) are implemented with pure Python standard libraries without native C/C++ library dependencies.
- **Unified Querying & Storage**: Ingested messages from diverse providers (Gmail, Outlook, Thunderbird) are normalized into a single database schema with source prefix isolation (`gmail:`, `outlook:`, `thunderbird:`).

## Functional Requirements

1. Support importing messages from: Gmail, Outlook PST files, Thunderbird PCV files
2. Support exporting messages as Markdown or standard .eml files into hierarchical date-bucketed directories (`<output_dir>/<YYYY>/<MM>/`)
3. Support basic filter operations during import and export
4. Support stats gathering w.r.t.: number of messages, number of labels, number of to/from addresses
5. Support searching imported messages

## Technical Requirements & Invariants

1. 3rd Party dependencies limited to: Python and SQLite
2. All functionalities are covered by tests
3. Project complies with [cross-project development guidelines](https://github.com/gpellicciotta/dev-guidelines)

