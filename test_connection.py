#!/usr/bin/env python3
"""Sanity-check Yahoo IMAP credentials and connectivity.

Not part of the MCP server itself — run this directly to confirm YAHOO_EMAIL
and YAHOO_APP_PASSWORD (from .env or the shell environment) work before
wiring the server into Claude.

Usage:
    python test_connection.py
"""

import sys

from server import ConfigError, _decode_mime, _format_address, _sort_key, imap_connection


def main():
    try:
        with imap_connection() as client:
            print("Connected and authenticated successfully.\n")

            folders = client.list_folders()
            print(f"Found {len(folders)} folder(s):")
            for flags, _delimiter, name in folders:
                flag_strs = [f.decode() if isinstance(f, bytes) else f for f in flags]
                print(f"  - {name}  {flag_strs}")

            print("\nMost recent 3 emails in INBOX:")
            client.select_folder("INBOX", readonly=True)
            uids = client.search(["ALL"])
            if not uids:
                print("  (no messages)")
                return

            fetched = client.fetch(uids, ["ENVELOPE"])
            items = [(uid, data.get(b"ENVELOPE")) for uid, data in fetched.items()]
            items.sort(key=lambda item: _sort_key(item[1].date if item[1] else None), reverse=True)

            for uid, envelope in items[:3]:
                subject = _decode_mime(envelope.subject) if envelope and envelope.subject else "(no subject)"
                sender = (
                    _format_address(envelope.from_[0])
                    if envelope and envelope.from_
                    else "(unknown sender)"
                )
                msg_date = envelope.date.isoformat() if envelope and envelope.date else "(no date)"
                print(f"  UID {uid} | {msg_date} | {sender} | {subject}")

    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
