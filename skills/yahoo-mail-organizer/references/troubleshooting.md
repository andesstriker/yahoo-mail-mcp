# Troubleshooting

| `error_type` | Meaning | Fix |
|---|---|---|
| `config` | Missing or rejected credentials | Check `YAHOO_EMAIL` and `YAHOO_APP_PASSWORD` in `.env`. Regenerate the App Password (revoked ones stop working). Two-step verification must be on. |
| `folder_not_found` | Folder name wrong or not selectable | Run `list_folders` and use the exact name (case and spacing matter). |
| `message_not_found` | UID not in that folder | UIDs are per-folder. Re-run `list_emails` / `search_emails` and use the folder the UID came from. |
| `attachment_not_found` | Filename mismatch | Use the exact filename from `read_email`'s `attachments` list. |
| `invalid_argument` | Bad input, usually dates | Use `YYYY-MM-DD`. |
| `imap_error` | Yahoo rejected the command | Retry once; if it persists, test with `python test_connection.py`. |
| `connection_error` | Network/TLS problem | Check connectivity to `imap.mail.yahoo.com:993`. |

If the `yahoo-mail` tools don't appear at all, the MCP server isn't registered or the agent wasn't restarted; see `setup.md`.
