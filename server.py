"""Yahoo Mail MCP server.

Exposes IMAP-backed tools (list/search/read/move/delete/mark) for a Yahoo
Mail account over the Model Context Protocol. Every tool opens a short-lived
IMAP connection, does its work, and closes it — connections are never held
open across calls.
"""

import base64
import email
import functools
import imaplib
import os
import ssl
from contextlib import contextmanager
from datetime import date, datetime, timezone
from email.header import decode_header
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
from mcp.server.fastmcp import FastMCP

# Load .env from this file's own directory, not the process's cwd — the cwd
# an MCP client launches this server with is not guaranteed to be this
# project's root.
load_dotenv(Path(__file__).resolve().parent / ".env")

YAHOO_IMAP_HOST = "imap.mail.yahoo.com"
YAHOO_IMAP_PORT = 993

mcp = FastMCP("yahoo-mail-mcp")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when required environment variables are missing or invalid."""


class FolderNotFoundError(Exception):
    """Raised when a requested IMAP folder doesn't exist or can't be found."""


class MessageNotFoundError(Exception):
    """Raised when a UID doesn't resolve to a message in the selected folder."""


class AttachmentNotFoundError(Exception):
    """Raised when a named attachment can't be found on a message."""


# --------------------------------------------------------------------------
# Connection helper — the one place that opens an IMAP connection
# --------------------------------------------------------------------------

@contextmanager
def imap_connection():
    """Open a short-lived, authenticated IMAP connection to Yahoo Mail.

    Reads YAHOO_EMAIL / YAHOO_APP_PASSWORD from the environment (populated
    via .env by python-dotenv). Yields an imapclient.IMAPClient configured
    with use_uid=True so every operation addresses messages by UID. Always
    logs out in a finally block — never call this and hold the connection
    open across multiple tool invocations.
    """
    yahoo_email = os.environ.get("YAHOO_EMAIL")
    app_password = os.environ.get("YAHOO_APP_PASSWORD")
    if not yahoo_email or not app_password:
        raise ConfigError(
            "Missing YAHOO_EMAIL and/or YAHOO_APP_PASSWORD environment variables. "
            "Set them in a .env file (see .env.example) or your shell environment. "
            "YAHOO_APP_PASSWORD must be a Yahoo App Password, not your regular "
            "account password — generate one at "
            "https://login.yahoo.com/account/security under 'Generate app password' "
            "(requires Two-step verification to be enabled on the account)."
        )

    client = IMAPClient(YAHOO_IMAP_HOST, port=YAHOO_IMAP_PORT, use_uid=True, ssl=True)
    try:
        try:
            client.login(yahoo_email, app_password)
        except imaplib.IMAP4.error as e:
            raise ConfigError(
                "Yahoo rejected the login. Double-check YAHOO_EMAIL and that "
                "YAHOO_APP_PASSWORD is a current App Password (regular account "
                "passwords will not work, and app passwords are invalidated if "
                "revoked or regenerated). Generate a fresh one at "
                "https://login.yahoo.com/account/security."
            ) from e
        yield client
    finally:
        try:
            client.logout()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Error-handling decorator — every tool wraps its IMAP work with this
# --------------------------------------------------------------------------

def imap_tool(func):
    """Run a tool body and translate exceptions into structured error dicts.

    Never lets a raw stack trace (which could echo connection internals)
    reach the caller — always returns {"error": ..., "error_type": ...}.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ConfigError as e:
            return {"error": str(e), "error_type": "config"}
        except FolderNotFoundError as e:
            return {"error": str(e), "error_type": "folder_not_found"}
        except MessageNotFoundError as e:
            return {"error": str(e), "error_type": "message_not_found"}
        except AttachmentNotFoundError as e:
            return {"error": str(e), "error_type": "attachment_not_found"}
        except ValueError as e:
            return {"error": str(e), "error_type": "invalid_argument"}
        except (IMAPClientError, imaplib.IMAP4.error) as e:
            return {"error": f"IMAP error: {e}", "error_type": "imap_error"}
        except (OSError, ssl.SSLError) as e:
            return {"error": f"Connection to Yahoo IMAP failed: {e}", "error_type": "connection_error"}
        except Exception as e:  # last-resort guard against leaking a raw traceback
            return {"error": f"Unexpected error: {e}", "error_type": "unknown"}

    return wrapper


# --------------------------------------------------------------------------
# Small shared helpers
# --------------------------------------------------------------------------

def _decode_mime(value):
    """Decode a MIME-encoded header value (bytes or str) into plain text."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    parts = []
    for text, encoding in decode_header(value):
        if isinstance(text, bytes):
            parts.append(text.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(text)
    return "".join(parts)


def _format_address(addr):
    """Format an imapclient envelope Address namedtuple as 'Name <user@host>'."""
    if addr is None:
        return None
    name = _decode_mime(addr.name) if addr.name else ""
    mailbox = addr.mailbox.decode() if addr.mailbox else ""
    host = addr.host.decode() if addr.host else ""
    address = f"{mailbox}@{host}" if mailbox and host else (mailbox or host)
    return f"{name} <{address}>" if name else address


def _sort_key(dt):
    """Normalize a possibly-None, possibly-naive datetime for sort comparisons."""
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_date(value, field_name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Invalid {field_name} date '{value}'; expected ISO format YYYY-MM-DD"
        ) from e


def _select_folder(client, folder):
    try:
        client.select_folder(folder)
    except Exception as e:
        raise FolderNotFoundError(f"Folder '{folder}' does not exist or is not selectable: {e}") from e


def _fetch_envelope(client, uid):
    """Fetch a message's envelope + flags, confirming it exists. Never mutates flags."""
    resp = client.fetch([uid], ["ENVELOPE", "FLAGS"])
    if uid not in resp:
        raise MessageNotFoundError(f"No message with UID {uid} in the selected folder.")
    return resp[uid]


def _summarize(uid, data):
    envelope = data.get(b"ENVELOPE")
    flags = data.get(b"FLAGS", ())
    return {
        "uid": uid,
        "subject": _decode_mime(envelope.subject) if envelope else None,
        "sender": _format_address(envelope.from_[0]) if envelope and envelope.from_ else None,
        "date": envelope.date.isoformat() if envelope and envelope.date else None,
        "unread": b"\\Seen" not in flags,
        "flagged": b"\\Flagged" in flags,
        "_sort_date": envelope.date if envelope else None,
    }


def _fetch_and_summarize(client, uids, limit):
    if not uids:
        return []
    fetched = client.fetch(uids, ["ENVELOPE", "FLAGS"])
    items = [_summarize(uid, data) for uid, data in fetched.items()]
    items.sort(key=lambda item: _sort_key(item["_sort_date"]), reverse=True)
    for item in items:
        item.pop("_sort_date", None)
    return items[:limit]


def _decode_part(part):
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _has_move_capability(client):
    capabilities = client.capabilities()
    return any(
        (cap.decode() if isinstance(cap, bytes) else cap).upper() == "MOVE"
        for cap in capabilities
    )


def _copy_delete_expunge(client, uids, to_folder):
    """Fallback for servers without MOVE: COPY, flag \\Deleted, then UID EXPUNGE."""
    client.copy(uids, to_folder)
    client.delete_messages(uids)
    try:
        client.expunge(messages=uids)  # UID EXPUNGE (RFC 4315) — scoped to these UIDs only
    except IMAPClientError:
        client.expunge()  # server lacks UIDPLUS; expunges any \Deleted messages present


def _find_trash_folder(client):
    """Find the mailbox's Trash folder via IMAP special-use flags, not a hardcoded name."""
    try:
        found = client.find_special_folder(b"\\Trash")
        if found:
            return found
    except Exception:
        pass

    folders = client.list_folders()
    for flags, _delimiter, name in folders:
        for flag in flags:
            flag_str = (flag.decode() if isinstance(flag, bytes) else flag).lower()
            if flag_str == "\\trash":
                return name

    for candidate in ("Trash", "Bin", "Deleted Items", "Deleted Messages"):
        for _flags, _delimiter, name in folders:
            if name.lower() == candidate.lower():
                return name

    return None


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

@mcp.tool()
@imap_tool
def create_folder(name: str) -> dict:
    """Create a new top-level IMAP folder if it doesn't already exist.

    Args:
        name: Folder name to create (e.g. "Noise").

    Idempotent: if a folder with this exact name already exists, does
    nothing and reports that instead of erroring.
    """
    with imap_connection() as client:
        existing = {folder_name for _flags, _delimiter, folder_name in client.list_folders()}
        if name in existing:
            return {"folder": name, "created": False, "already_existed": True}
        client.create_folder(name)
        return {"folder": name, "created": True, "already_existed": False}


@mcp.tool()
@imap_tool
def list_folders() -> dict:
    """List every IMAP folder/label available in the mailbox.

    Returns: {"folders": [{"name": str, "flags": [str, ...]}, ...]}
    Flags include IMAP special-use markers (e.g. "\\Trash", "\\Sent", "\\Junk")
    when the server advertises them.
    """
    with imap_connection() as client:
        result = []
        for flags, _delimiter, name in client.list_folders():
            flag_strs = [f.decode() if isinstance(f, bytes) else f for f in flags]
            result.append({"name": name, "flags": flag_strs})
        return {"folders": result}


@mcp.tool()
@imap_tool
def list_emails(folder: str = "INBOX", limit: int = 20, unread_only: bool = False) -> dict:
    """List recent emails in a folder, newest first.

    Args:
        folder: IMAP folder name to list (default "INBOX").
        limit: Maximum number of emails to return (default 20).
        unread_only: If True, only return messages without the \\Seen flag.

    Returns: {"folder": str, "count": int, "emails": [
        {"uid": int, "subject": str, "sender": str, "date": iso8601 str,
         "unread": bool, "flagged": bool}, ...
    ]}
    Does not mark anything as read.
    """
    with imap_connection() as client:
        _select_folder(client, folder)
        criteria = ["UNSEEN"] if unread_only else ["ALL"]
        uids = client.search(criteria)
        emails = _fetch_and_summarize(client, uids, limit)
        return {"folder": folder, "count": len(emails), "emails": emails}


@mcp.tool()
@imap_tool
def search_emails(
    folder: str = "INBOX",
    sender: Optional[str] = None,
    subject: Optional[str] = None,
    since: Optional[str] = None,
    before: Optional[str] = None,
    unread_only: bool = False,
    limit: int = 20,
) -> dict:
    """Search emails in a folder using an IMAP SEARCH built from the given filters.

    Args:
        folder: IMAP folder to search (default "INBOX").
        sender: Substring to match against the From header.
        subject: Substring to match against the Subject header.
        since: Only messages on/after this date, as an ISO string "YYYY-MM-DD".
        before: Only messages strictly before this date, as an ISO string "YYYY-MM-DD".
        unread_only: If True, restrict to messages without the \\Seen flag.
        limit: Maximum number of matches to return (default 20).

    Filters are combined with AND. If no filters are given, all messages in the
    folder are matched (subject to limit). Returns the same summary shape as
    list_emails, sorted newest first.
    """
    with imap_connection() as client:
        _select_folder(client, folder)

        criteria = []
        if unread_only:
            criteria.append("UNSEEN")
        if sender:
            criteria += ["FROM", sender]
        if subject:
            criteria += ["SUBJECT", subject]
        if since:
            criteria += ["SINCE", _parse_iso_date(since, "since")]
        if before:
            criteria += ["BEFORE", _parse_iso_date(before, "before")]
        if not criteria:
            criteria = ["ALL"]

        uids = client.search(criteria)
        emails = _fetch_and_summarize(client, uids, limit)
        return {"folder": folder, "count": len(emails), "emails": emails}


@mcp.tool()
@imap_tool
def read_email(uid: int, folder: str = "INBOX") -> dict:
    """Fetch the full content of one email by UID.

    Args:
        uid: The message's IMAP UID (as returned by list_emails/search_emails).
        folder: Folder the message lives in (default "INBOX").

    Returns headers (subject/from/to/cc/date/list_unsubscribe), a plain-text
    body (falling back to HTML stripped of markup if no text/plain part
    exists), and a list of attachment filenames only — attachment bytes are
    NOT fetched here, use get_attachment for that. list_unsubscribe is the
    raw List-Unsubscribe header value (or null if absent) — its presence is
    a common signal for bulk/marketing mail. Fetches with BODY.PEEK so the
    \\Seen flag is left untouched; use mark_email to change read/unread
    state explicitly.
    """
    with imap_connection() as client:
        _select_folder(client, folder)
        _fetch_envelope(client, uid)  # confirms the message exists

        fetched = client.fetch([uid], ["BODY.PEEK[]"])
        if uid not in fetched:
            raise MessageNotFoundError(f"No message with UID {uid} in folder '{folder}'.")

        msg = email.message_from_bytes(fetched[uid][b"BODY[]"])

        plain_body = None
        html_body = None
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                if part.is_multipart():
                    continue
                filename = part.get_filename()
                if filename:
                    attachments.append(_decode_mime(filename))
                    continue
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition") or "").lower()
                if "attachment" in disposition:
                    continue
                if content_type == "text/plain" and plain_body is None:
                    plain_body = _decode_part(part)
                elif content_type == "text/html" and html_body is None:
                    html_body = _decode_part(part)
        else:
            if msg.get_content_type() == "text/html":
                html_body = _decode_part(msg)
            else:
                plain_body = _decode_part(msg)

        if plain_body is not None:
            body = plain_body
        elif html_body is not None:
            body = BeautifulSoup(html_body, "html.parser").get_text(separator="\n").strip()
        else:
            body = ""

        return {
            "uid": uid,
            "folder": folder,
            "subject": _decode_mime(msg.get("Subject")),
            "from": _decode_mime(msg.get("From")),
            "to": _decode_mime(msg.get("To")),
            "cc": _decode_mime(msg.get("Cc")),
            "date": msg.get("Date"),
            "list_unsubscribe": msg.get("List-Unsubscribe"),
            "body": body,
            "attachments": attachments,
        }


@mcp.tool()
@imap_tool
def get_attachment(uid: int, filename: str, folder: str = "INBOX") -> dict:
    """Fetch one attachment's raw bytes (base64-encoded) from a message.

    Args:
        uid: The message's IMAP UID.
        filename: Exact attachment filename, as returned by read_email's
            "attachments" list.
        folder: Folder the message lives in (default "INBOX").

    Returns: {"uid": int, "filename": str, "content_type": str,
    "size_bytes": int, "content_base64": str}. Fails with an
    "attachment_not_found" error if no attachment on the message matches
    filename exactly.
    """
    with imap_connection() as client:
        _select_folder(client, folder)
        _fetch_envelope(client, uid)

        fetched = client.fetch([uid], ["BODY.PEEK[]"])
        if uid not in fetched:
            raise MessageNotFoundError(f"No message with UID {uid} in folder '{folder}'.")

        msg = email.message_from_bytes(fetched[uid][b"BODY[]"])
        for part in msg.walk():
            part_filename = part.get_filename()
            if part_filename and _decode_mime(part_filename) == filename:
                payload = part.get_payload(decode=True) or b""
                return {
                    "uid": uid,
                    "filename": filename,
                    "content_type": part.get_content_type(),
                    "size_bytes": len(payload),
                    "content_base64": base64.b64encode(payload).decode("ascii"),
                }

        raise AttachmentNotFoundError(f"No attachment named '{filename}' found on message UID {uid}.")


@mcp.tool()
@imap_tool
def move_email(uid: int, from_folder: str, to_folder: str) -> dict:
    """Move a single email between folders by UID.

    Args:
        uid: The message's IMAP UID in from_folder.
        from_folder: Folder the message currently lives in.
        to_folder: Destination folder name (must already exist).

    Confirms the message exists before acting. Uses IMAP MOVE if the server
    supports it, otherwise falls back to COPY + flag \\Deleted + UID EXPUNGE
    (which only expunges the message just moved, never the whole folder).
    Returns the subject/sender of the message that was moved, so the caller
    can verify the right email was touched.
    """
    with imap_connection() as client:
        _select_folder(client, from_folder)
        envelope_data = _fetch_envelope(client, uid)
        envelope = envelope_data.get(b"ENVELOPE")
        subject = _decode_mime(envelope.subject) if envelope else None
        sender = _format_address(envelope.from_[0]) if envelope and envelope.from_ else None

        if _has_move_capability(client):
            client.move([uid], to_folder)
            method = "MOVE"
        else:
            _copy_delete_expunge(client, [uid], to_folder)
            method = "COPY+STORE+EXPUNGE"

        return {
            "uid": uid,
            "from_folder": from_folder,
            "to_folder": to_folder,
            "subject": subject,
            "sender": sender,
            "method": method,
        }


@mcp.tool()
@imap_tool
def delete_email(uid: int, folder: str = "INBOX", permanent: bool = False) -> dict:
    """Delete a single email by UID. Defaults to a safe, recoverable soft-delete.

    Args:
        uid: The message's IMAP UID.
        folder: Folder the message currently lives in (default "INBOX").
        permanent: If False (the default), the message is MOVED to the
            mailbox's Trash folder (found via IMAP special-use flags, not a
            hardcoded name) and can be recovered from there. If True, the
            message is immediately flagged \\Deleted and expunged — this is
            NOT recoverable. Only pass permanent=True when the caller has
            explicitly asked for permanent deletion.

    Confirms the message exists before acting and returns the subject/sender
    of what was deleted, so the caller can verify the right email was
    touched. Only ever expunges the single UID acted on, never a whole
    folder.
    """
    with imap_connection() as client:
        _select_folder(client, folder)
        envelope_data = _fetch_envelope(client, uid)
        envelope = envelope_data.get(b"ENVELOPE")
        subject = _decode_mime(envelope.subject) if envelope else None
        sender = _format_address(envelope.from_[0]) if envelope and envelope.from_ else None

        if not permanent:
            trash_folder = _find_trash_folder(client)
            if trash_folder is None:
                raise FolderNotFoundError(
                    "Could not locate a Trash folder via IMAP special-use flags or "
                    "common naming conventions. Pass permanent=True to hard-delete "
                    "instead, or use move_email to move it to a folder you specify."
                )
            if _has_move_capability(client):
                client.move([uid], trash_folder)
                method = "MOVE"
            else:
                _copy_delete_expunge(client, [uid], trash_folder)
                method = "COPY+STORE+EXPUNGE"
            return {
                "uid": uid,
                "folder": folder,
                "action": "trashed",
                "trash_folder": trash_folder,
                "subject": subject,
                "sender": sender,
                "method": method,
            }

        client.delete_messages([uid])
        try:
            client.expunge(messages=[uid])
        except IMAPClientError:
            client.expunge()
        return {
            "uid": uid,
            "folder": folder,
            "action": "permanently_deleted",
            "subject": subject,
            "sender": sender,
        }


@mcp.tool()
@imap_tool
def mark_email(uid: int, folder: str = "INBOX", read: bool = True) -> dict:
    """Set or unset the read (\\Seen) flag on a single email.

    Args:
        uid: The message's IMAP UID.
        folder: Folder the message lives in (default "INBOX").
        read: True to mark as read (add \\Seen), False to mark as unread
            (remove \\Seen). Defaults to True.

    Confirms the message exists before acting.
    """
    with imap_connection() as client:
        _select_folder(client, folder)
        _fetch_envelope(client, uid)
        if read:
            client.add_flags([uid], [b"\\Seen"])
        else:
            client.remove_flags([uid], [b"\\Seen"])
        return {"uid": uid, "folder": folder, "read": read}


if __name__ == "__main__":
    mcp.run()
