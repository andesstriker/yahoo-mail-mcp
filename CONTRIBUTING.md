# Contributing

Issues and pull requests are welcome.

## Local setup

Follow the [README](README.md) setup steps (install dependencies into a venv,
copy `.env.example` to `.env` with your own Yahoo credentials). Before
submitting a PR, run:

```bash
python test_connection.py
```

against your own Yahoo account to confirm nothing broke basic connectivity.

## CI

The GitHub Actions workflow only checks that the code compiles and imports
cleanly across supported Python versions — it has no Yahoo credentials
available, so it cannot exercise real IMAP behavior. If you're changing
anything inside `imap_connection()` or any of the `@mcp.tool()` functions,
please test it manually against a real mailbox and describe what you tested
in the PR description.

## Scope

Keep changes focused — this is a small, single-file MCP server by design.
Prefer extending an existing tool's parameters over adding a new tool when
the behavior is closely related.
