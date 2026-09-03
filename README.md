# yahoo-mail-mcp

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![MCP](https://img.shields.io/badge/MCP-compatible-6b46c1.svg)

> Read, search, organize, and clean up a Yahoo Mail account from Claude — over plain IMAP, no Yahoo API keys required.

An MCP (Model Context Protocol) server that lets an LLM read, search, move,
and delete emails in a Yahoo Mail account over IMAP.

Tools exposed: `list_folders`, `create_folder`, `list_emails`, `search_emails`,
`read_email`, `get_attachment`, `move_email`, `delete_email`, `mark_email`.

Every tool opens a short-lived IMAP connection, does its work, and closes it.
Deletion defaults to moving messages to Trash (found via IMAP special-use
flags, not a hardcoded name) — permanent deletion requires the caller to
explicitly pass `permanent=True`. No tool can delete or expunge an entire
folder; only single messages by UID.

## 1. Enable IMAP on your Yahoo account

IMAP access is on by default for most Yahoo Mail accounts. If mail clients
can't connect, check: **Yahoo Mail → Settings → More Settings → Mailboxes →
[your account] → "Allow apps that use less secure sign in"** is *not* the
setting you want here — that's for legacy password auth. Modern Yahoo
requires an **App Password** instead (see below), which works whether or not
that legacy toggle is on. If you still see connection issues, sign in to
[Yahoo Account Security](https://login.yahoo.com/account/security) and
confirm the account isn't locked or flagged for suspicious activity.

## 2. Generate a Yahoo App Password

Yahoo blocks IMAP logins using your normal account password once two-step
verification is enabled (and recommends app passwords generally). To
generate one:

1. Go to <https://login.yahoo.com/account/security>.
2. Turn on **Two-step verification** if it isn't already on (required for
   app passwords).
3. Find **"Generate app password"** (sometimes under "App passwords" /
   "Manage app passwords").
4. Choose "Other app", name it something like `yahoo-mail-mcp`, and generate.
5. Copy the generated password (usually 16 characters, no spaces) — Yahoo
   only shows it once.

Use this app password as `YAHOO_APP_PASSWORD`, never your real account
password.

## 3. Install dependencies

Requires Python 3.10+.

```bash
cd yahoo-mail-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
YAHOO_EMAIL=you@yahoo.com
YAHOO_APP_PASSWORD=your16charapppassword
```

`.env` is already in `.gitignore` — never commit it.

## 5. Sanity-check connectivity

Before wiring the server into Claude, confirm your credentials work:

```bash
python test_connection.py
```

This logs in, lists your folders, and prints the 3 most recent inbox emails.
It never prints your app password.

## 6. Run the server

```bash
python server.py
```

The server speaks MCP over stdio — it's meant to be launched by an MCP
client (Claude Desktop, Claude Code), not run standalone for interactive use.

## 7. Register with Claude Desktop / Claude Code

Add an entry to your MCP config pointing at this project's venv Python and
`server.py`. Use absolute paths.

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`
on macOS):

```json
{
  "mcpServers": {
    "yahoo-mail": {
      "command": "/absolute/path/to/yahoo-mail-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/yahoo-mail-mcp/server.py"],
      "env": {
        "YAHOO_EMAIL": "you@yahoo.com",
        "YAHOO_APP_PASSWORD": "your16charapppassword"
      }
    }
  }
}
```

**Claude Code** — add the same server via the CLI:

```bash
claude mcp add yahoo-mail /absolute/path/to/yahoo-mail-mcp/.venv/bin/python /absolute/path/to/yahoo-mail-mcp/server.py
```

or add it directly to your Claude Code MCP config file with the same JSON
shape as above.

If you'd rather not put the app password in the MCP config's `env` block,
omit `env` there and rely on `.env` next to `server.py` instead — the server
loads it automatically via `python-dotenv`.

Restart Claude Desktop / Claude Code after editing the config so it picks up
the new server.

## Usage

Once registered, just talk to Claude naturally — it will pick the right tool
automatically. For example:

- "List my unread emails"
- "Search for emails from newsletter@example.com since 2026-01-01"
- "Read that email from Sarah about the contract"
- "Download the attachment from that invoice email"
- "Create a folder called Receipts"
- "Move this email to the Receipts folder"
- "Move this email to trash" / "Permanently delete this spam email"
- "Mark that email as read" / "Mark it as unread"
- "What folders do I have in this mailbox?"

### Tool reference

| Tool | Purpose | Key parameters |
|---|---|---|
| `list_folders` | List every IMAP folder/label, with special-use flags | *(none)* |
| `create_folder` | Create a folder if it doesn't already exist (idempotent) | `name` |
| `list_emails` | List recent emails in a folder, newest first | `folder="INBOX"`, `limit=20`, `unread_only=False` |
| `search_emails` | Search a folder by sender/subject/date range/unread, AND-combined | `folder`, `sender`, `subject`, `since` (`YYYY-MM-DD`), `before`, `unread_only`, `limit` |
| `read_email` | Fetch full headers + body (plain text, or HTML stripped) + attachment filenames | `uid`, `folder="INBOX"` |
| `get_attachment` | Fetch one attachment's raw bytes, base64-encoded | `uid`, `filename`, `folder="INBOX"` |
| `move_email` | Move a single message between folders by UID | `uid`, `from_folder`, `to_folder` |
| `delete_email` | Delete a message — soft-delete (Trash) by default | `uid`, `folder="INBOX"`, `permanent=False` |
| `mark_email` | Set/unset the read (`\Seen`) flag | `uid`, `folder="INBOX"`, `read=True` |

## Notes on safety behavior

- `delete_email(permanent=False)` (the default) moves the message to Trash
  and is recoverable. `permanent=True` immediately expunges it — the caller
  must opt in explicitly.
- `move_email` and `delete_email` fetch the message's envelope first to
  confirm it exists, and return its subject/sender in the result so you can
  verify the right email was touched.
- All operations address messages by IMAP UID, which stays valid across
  sessions (never sequence numbers, which can shift).
- IMAP errors are returned to the caller as structured
  `{"error": ..., "error_type": ...}` dicts rather than raw exceptions/stack
  traces.

## Disclaimer

This is an independent, unofficial project. It is not affiliated with,
endorsed by, or sponsored by Yahoo, Oath/Verizon Media, or Anthropic. It
communicates with Yahoo Mail using the standard IMAP protocol and an
account-scoped App Password — no Yahoo API keys or OAuth are involved. Use
of this tool is subject to Yahoo's own Terms of Service. Provided as-is,
with no warranty — see [LICENSE](LICENSE).

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
