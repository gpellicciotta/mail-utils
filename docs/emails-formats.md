# Standard & Well-Known Email Formats

## Single-Message Formats
- **`.eml` (Electronic Mail)** *(De facto standard)*
  * **Standard**: Based on RFC 822 / RFC 5322 and MIME (RFC 2045–2049).
  * **Structure**: Plain text file containing headers (`From:`, `To:`, `Subject:`, etc.), body, and MIME-encoded attachments (Base64).
  * **Compatibility**: Universal. Supported by Thunderbird, Apple Mail, Windows Mail, Outlook, Python (`email` module), and most email APIs/tools.

- **`.msg` (Outlook Message Format)**
  * **Standard**: Proprietary Microsoft format (OLE / Compound File Binary format).
  * **Structure**: Binary container holding MAPI properties, message text, and attachments.
  * **Compatibility**: Primarily Microsoft Outlook and Exchange.

- **`.emlx` (Apple Mail Format)**
  * **Structure**: Plain `.eml` data preceded by a byte count header and followed by an Apple XML/plist metadata dictionary.

## Multi-Message / Mailbox Storage Formats
- **Mbox (`.mbox` or extensionless files)** *(Standard)*
  * **Standard**: RFC 4155.
  * **Structure**: A single plain-text file containing multiple concatenated email messages, each separated by a delimiter line starting with `From `.
  * **Compatibility**: Thunderbird (which creates `.msf` companion indexes for it), Unix/Linux mail systems, and Google Takeout mailbox exports.

- **Maildir (Directory-based)**
  * **Structure**: A folder structure containing `cur/`, `new/`, and `tmp/` subdirectories, where every email is stored as an individual file.
  * **Compatibility**: Linux/Unix mail servers (Dovecot, Postfix, Exim) and modern mail utilities. Avoids file-locking issues found in Mbox.

- **`.pst` / `.ost` (Personal / Offline Storage Table)**
  * **Standard**: Microsoft Outlook database file format.
  * **Structure**: Binary database containing entire mailboxes (folders, emails, calendars, tasks, contacts).

---

### Quick Summary

| Format | Scope | Type | Primary Use Case |
| :--- | :--- | :--- | :--- |
| **`.eml`** | Single Message | Plain text (RFC 5322 MIME) | **Best format for archiving / sharing individual emails** |
| **`.msg`** | Single Message | Binary (OLE/MAPI) | Microsoft Outlook specific exports |
| **`.mbox`** | Mailbox (Multi) | Plain text (Concatenated) | **Standard for full mailbox archives/exports** |
| **Maildir** | Mailbox (Multi) | Directory of individual files | Modern mail server storage |
| **`.msf`** | Index Only | Mork DB format | Thunderbird local mailbox index (not standalone) |
| **`.pst`** | Full Mailbox | Binary Database | Microsoft Outlook full archive/backup |