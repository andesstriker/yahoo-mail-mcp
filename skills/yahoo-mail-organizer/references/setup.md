# Setup

This skill does not talk to Yahoo itself. It guides an agent that has the **yahoo-mail MCP server** connected. Source and license (MIT): https://github.com/andesstriker/yahoo-mail-mcp

## 1. Create a Yahoo App Password
1. Open https://login.yahoo.com/account/security and enable Two-step verification.
2. Choose "Generate app password", pick "Other app", name it `yahoo-mail-mcp`.
3. Copy the password (shown once). Use it only in the config below, never in chat.

## 2. Install the server (Python 3.10+)
```bash
git clone https://github.com/andesstriker/yahoo-mail-mcp
cd yahoo-mail-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in YAHOO_EMAIL and YAHOO_APP_PASSWORD
python test_connection.py
```

## 3. Register it with your agent
Claude Code:
```bash
claude mcp add yahoo-mail /absolute/path/to/yahoo-mail-mcp/.venv/bin/python /absolute/path/to/yahoo-mail-mcp/server.py
```
Claude Desktop / Cursor: add an `mcpServers` entry named `yahoo-mail` with `command` set to the venv Python and `args` set to `["/absolute/path/to/server.py"]`. Credentials are read from the `.env` file next to `server.py`. Restart the agent afterwards.

## 4. Verify
Ask: "List my Yahoo folders." You should see Inbox, Sent, Trash and any custom folders.

What the server connects to: `imap.mail.yahoo.com:993` (TLS) only. It cannot send mail.
