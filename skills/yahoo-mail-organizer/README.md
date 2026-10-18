# Yahoo Mail Organizer (agent skill)

Teaches your AI agent to triage, search, and clean up a Yahoo Mail inbox safely using the open-source `yahoo-mail` MCP server.

- Soft-delete by default; confirmation before any bulk change
- Triage playbook for receipts, newsletters, and notifications
- Clear table output and undo guidance
- Prompt-injection guardrail: email content is treated as data

**Requires** the yahoo-mail MCP server (free, MIT): see `references/setup.md`. Independent project; not affiliated with Yahoo or Anthropic.

Install: unzip so the folder `yahoo-mail-organizer/` sits in `~/.claude/skills/` (or your agent's skills directory).
