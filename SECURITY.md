# Security

## Reporting a vulnerability

Please open a GitHub issue describing the problem. Avoid including real
credentials, email content, or other personal data in the report.

## Handling credentials

- Always use a Yahoo **App Password** (generated at
  [login.yahoo.com/account/security](https://login.yahoo.com/account/security)),
  never your real account password. See the README for how to generate one.
- Never commit a `.env` file. The provided `.gitignore` already excludes it —
  don't remove that entry.
- The app password and email address are only ever read from environment
  variables and are never logged, printed, or included in error messages
  (see `imap_connection()` and the `imap_tool` error-handling decorator in
  `server.py`).

## Destructive operations

`delete_email` and `move_email` act on a single message by UID and confirm
the message exists before acting, but they still make real changes to your
mailbox. `delete_email` defaults to a recoverable soft-delete (move to
Trash) — permanent deletion requires the caller to explicitly pass
`permanent=True`. Whatever MCP client you use (Claude Desktop, Claude Code,
etc.), review what a proposed tool call will actually do before approving
it, especially for destructive requests phrased in bulk ("delete all my
promotional emails").
